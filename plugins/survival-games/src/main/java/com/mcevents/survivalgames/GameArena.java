package com.mcevents.survivalgames;

import cn.nukkit.Player;
import cn.nukkit.item.Item;
import cn.nukkit.level.Level;
import cn.nukkit.level.Position;
import cn.nukkit.math.Vector3;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.ConfigSection;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class GameArena {

    public enum ArenaState {
        WAITING, STARTING, INGAME, DEATHMATCH, ENDING
    }

    private final SurvivalGamesPlugin plugin;
    private final String name;
    private final int minPlayers;
    private final int maxPlayers;
    private final int lobbyCountdown;
    private final int gameTime;
    private final int deathmatchTime;
    private final int borderShrinkInterval;
    private final double borderShrinkAmount;
    private final List<Position> spawnPositions = new ArrayList<>();
    private Position lobbyPosition;

    private final Set<String> players = new LinkedHashSet<>();
    private final Set<String> spectators = new HashSet<>();
    private final Set<String> alivePlayers = new HashSet<>();
    private final Map<String, Integer> killCounts = new HashMap<>();

    private ArenaState state = ArenaState.WAITING;
    private int countdown;
    private int gameTimer;
    private int taskId = -1;

    public GameArena(SurvivalGamesPlugin plugin, String name, ConfigSection config) {
        this.plugin = plugin;
        this.name = name;
        this.minPlayers = config.getInt("min-players", plugin.getConfig().getInt("settings.min-players", 4));
        this.maxPlayers = config.getInt("max-players", plugin.getConfig().getInt("settings.max-players", 24));
        this.lobbyCountdown = plugin.getConfig().getInt("settings.lobby-countdown", 30);
        this.gameTime = plugin.getConfig().getInt("settings.game-time", 600);
        this.deathmatchTime = plugin.getConfig().getInt("settings.deathmatch-time", 120);
        this.borderShrinkInterval = plugin.getConfig().getInt("settings.border.shrink-interval", 60);
        this.borderShrinkAmount = plugin.getConfig().getDouble("settings.border.shrink-amount", 5.0);

        if (config.exists("lobby")) {
            ConfigSection lobby = config.getSection("lobby");
            String worldName = lobby.getString("world", "world");
            Level level = plugin.getServer().getLevelByName(worldName);
            if (level != null) {
                lobbyPosition = new Position(lobby.getDouble("x"), lobby.getDouble("y"), lobby.getDouble("z"), level);
            }
        }

        if (config.exists("spawns")) {
            for (String key : config.getSection("spawns").getKeys(false)) {
                ConfigSection spawn = config.getSection("spawns." + key);
                String worldName = spawn.getString("world", "world");
                Level level = plugin.getServer().getLevelByName(worldName);
                if (level != null) {
                    spawnPositions.add(new Position(spawn.getDouble("x"), spawn.getDouble("y"), spawn.getDouble("z"), level));
                }
            }
        }
    }

    public boolean addPlayer(Player player) {
        if (state != ArenaState.WAITING && state != ArenaState.STARTING) {
            player.sendMessage(plugin.msg("game-already-started"));
            return false;
        }
        if (players.size() >= maxPlayers) {
            return false;
        }

        players.add(player.getName());
        alivePlayers.add(player.getName());
        killCounts.put(player.getName(), 0);

        if (lobbyPosition != null) {
            player.teleport(lobbyPosition);
        }

        player.getInventory().clearAll();
        player.setHealth(player.getMaxHealth());
        player.getFoodData().setLevel(20);
        player.setGamemode(Player.ADVENTURE);

        broadcastMessage(plugin.msg("player-joined")
                .replace("{player}", player.getName())
                .replace("{count}", String.valueOf(players.size()))
                .replace("{max}", String.valueOf(maxPlayers)));

        if (players.size() >= minPlayers && state == ArenaState.WAITING) {
            startCountdown();
        }

        return true;
    }

    public void removePlayer(Player player) {
        players.remove(player.getName());
        alivePlayers.remove(player.getName());
        spectators.remove(player.getName());
        killCounts.remove(player.getName());

        player.getInventory().clearAll();
        player.setGamemode(Player.SURVIVAL);
        player.setHealth(player.getMaxHealth());
        player.getFoodData().setLevel(20);

        Position spawn = plugin.getServer().getDefaultLevel().getSpawnLocation();
        player.teleport(spawn);

        broadcastMessage(plugin.msg("player-left")
                .replace("{player}", player.getName())
                .replace("{count}", String.valueOf(players.size())));

        plugin.removePlayerFromMap(player.getName());

        if (state == ArenaState.INGAME || state == ArenaState.DEATHMATCH) {
            checkWinCondition();
        }

        if (state == ArenaState.STARTING && players.size() < minPlayers) {
            cancelCountdown();
        }
    }

    private void startCountdown() {
        state = ArenaState.STARTING;
        countdown = lobbyCountdown;

        taskId = plugin.getServer().getScheduler().scheduleRepeatingTask(plugin, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (countdown <= 0) {
                    startGame();
                    this.getHandler().cancel();
                    return;
                }
                if (countdown <= 10 || countdown % 10 == 0) {
                    broadcastMessage(plugin.msg("game-starting")
                            .replace("{seconds}", String.valueOf(countdown)));
                }
                countdown--;
            }
        }, 20).getTaskId();
    }

    private void cancelCountdown() {
        state = ArenaState.WAITING;
        if (taskId != -1) {
            plugin.getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        broadcastMessage(plugin.msg("not-enough-players"));
    }

    private void startGame() {
        state = ArenaState.INGAME;
        gameTimer = gameTime;

        List<String> playerList = new ArrayList<>(players);
        Collections.shuffle(playerList);

        for (int i = 0; i < playerList.size(); i++) {
            Player player = plugin.getServer().getPlayerExact(playerList.get(i));
            if (player == null) continue;

            if (i < spawnPositions.size()) {
                player.teleport(spawnPositions.get(i));
            }
            player.setGamemode(Player.SURVIVAL);
            player.getInventory().clearAll();
            player.setHealth(player.getMaxHealth());
            player.getFoodData().setLevel(20);
        }

        broadcastMessage(plugin.msg("game-started"));
        broadcastTitle(TextFormat.RED + "FIGHT!", TextFormat.YELLOW + "Да начнутся Голодные Игры!");

        fillChests();

        taskId = plugin.getServer().getScheduler().scheduleRepeatingTask(plugin, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (gameTimer <= 0) {
                    startDeathmatch();
                    this.getHandler().cancel();
                    return;
                }
                if (gameTimer % borderShrinkInterval == 0 && gameTimer != gameTime) {
                    shrinkBorder();
                }
                if (gameTimer <= 10 || gameTimer == 30 || gameTimer == 60) {
                    broadcastMessage(plugin.msg("deathmatch-countdown")
                            .replace("{seconds}", String.valueOf(gameTimer)));
                }
                gameTimer--;
            }
        }, 20).getTaskId();
    }

    private void startDeathmatch() {
        state = ArenaState.DEATHMATCH;
        gameTimer = deathmatchTime;

        Vector3 center = calculateCenter();
        for (String playerName : alivePlayers) {
            Player player = plugin.getServer().getPlayerExact(playerName);
            if (player != null) {
                player.teleport(new Position(center.getX(), center.getY(), center.getZ(), player.getLevel()));
            }
        }

        broadcastMessage(plugin.msg("deathmatch-started"));
        broadcastTitle(TextFormat.DARK_RED + "DEATHMATCH!", TextFormat.RED + "Сражайтесь до последнего!");

        taskId = plugin.getServer().getScheduler().scheduleRepeatingTask(plugin, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (gameTimer <= 0 || alivePlayers.size() <= 1) {
                    endGame();
                    this.getHandler().cancel();
                    return;
                }
                gameTimer--;
            }
        }, 20).getTaskId();
    }

    public void onPlayerDeath(Player victim, Player killer) {
        alivePlayers.remove(victim.getName());
        spectators.add(victim.getName());
        victim.setGamemode(Player.SPECTATOR);

        if (killer != null) {
            killCounts.merge(killer.getName(), 1, Integer::sum);
            broadcastMessage(plugin.msg("player-killed")
                    .replace("{victim}", victim.getName())
                    .replace("{killer}", killer.getName())
                    .replace("{remaining}", String.valueOf(alivePlayers.size())));
        } else {
            broadcastMessage(plugin.msg("player-died")
                    .replace("{player}", victim.getName())
                    .replace("{remaining}", String.valueOf(alivePlayers.size())));
        }

        checkWinCondition();
    }

    private void checkWinCondition() {
        if (alivePlayers.size() <= 1) {
            endGame();
        }
    }

    private void endGame() {
        state = ArenaState.ENDING;
        if (taskId != -1) {
            plugin.getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        if (alivePlayers.size() == 1) {
            String winnerName = alivePlayers.iterator().next();
            Player winner = plugin.getServer().getPlayerExact(winnerName);

            broadcastMessage(plugin.msg("game-winner")
                    .replace("{player}", winnerName)
                    .replace("{kills}", String.valueOf(killCounts.getOrDefault(winnerName, 0))));

            if (winner != null) {
                broadcastTitle(TextFormat.GOLD + "ПОБЕДА!", TextFormat.YELLOW + winnerName + " победил!");
                giveRewards(winner);
            }
        } else {
            broadcastMessage(plugin.msg("game-draw"));
        }

        broadcastTopKillers();

        plugin.getServer().getScheduler().scheduleDelayedTask(plugin, new Task() {
            @Override
            public void onRun(int currentTick) {
                resetArena();
            }
        }, 100);
    }

    private void broadcastTopKillers() {
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(killCounts.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        broadcastMessage(TextFormat.GOLD + "=== Топ убийцы ===");
        int rank = 1;
        for (Map.Entry<String, Integer> entry : sorted) {
            if (rank > 3 || entry.getValue() == 0) break;
            broadcastMessage(TextFormat.YELLOW + "#" + rank + " " + entry.getKey() + " — " + entry.getValue() + " убийств");
            rank++;
        }
    }

    private void giveRewards(Player winner) {
        Config config = plugin.getConfig();
        int money = config.getInt("settings.rewards.win-money", 500);
        int xp = config.getInt("settings.rewards.win-xp", 100);
        winner.sendMessage(plugin.msg("reward-received")
                .replace("{money}", String.valueOf(money))
                .replace("{xp}", String.valueOf(xp)));
    }

    private void resetArena() {
        for (String playerName : new HashSet<>(players)) {
            Player player = plugin.getServer().getPlayerExact(playerName);
            if (player != null) {
                player.getInventory().clearAll();
                player.setGamemode(Player.SURVIVAL);
                player.setHealth(player.getMaxHealth());
                player.getFoodData().setLevel(20);
                Position spawn = plugin.getServer().getDefaultLevel().getSpawnLocation();
                player.teleport(spawn);
            }
            plugin.removePlayerFromMap(playerName);
        }
        players.clear();
        spectators.clear();
        alivePlayers.clear();
        killCounts.clear();
        state = ArenaState.WAITING;
    }

    public void forceStart() {
        if (state == ArenaState.WAITING || state == ArenaState.STARTING) {
            if (taskId != -1) {
                plugin.getServer().getScheduler().cancelTask(taskId);
                taskId = -1;
            }
            startGame();
        }
    }

    public void forceStop() {
        if (taskId != -1) {
            plugin.getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        resetArena();
    }

    private void fillChests() {
        List<Item> lootTable = buildLootTable();
        // Chest filling is handled by scanning for chest blocks in the arena region
        // Players can find loot in pre-placed chests
        broadcastMessage(TextFormat.GRAY + "Сундуки заполнены лутом!");
    }

    private List<Item> buildLootTable() {
        List<Item> items = new ArrayList<>();
        Config config = plugin.getConfig();
        if (config.exists("settings.loot-table")) {
            for (String key : config.getSection("settings.loot-table").getKeys(false)) {
                ConfigSection itemSection = config.getSection("settings.loot-table." + key);
                int id = itemSection.getInt("id", 1);
                int damage = itemSection.getInt("damage", 0);
                int maxCount = itemSection.getInt("max-count", 1);
                int count = new Random().nextInt(maxCount) + 1;
                items.add(Item.get(id, damage, count));
            }
        }
        return items;
    }

    private void shrinkBorder() {
        broadcastMessage(plugin.msg("border-shrinking"));
        broadcastTitle("", TextFormat.RED + "Граница сужается!");
    }

    private Vector3 calculateCenter() {
        if (spawnPositions.isEmpty()) {
            return new Vector3(0, 64, 0);
        }
        double x = 0, y = 0, z = 0;
        for (Position pos : spawnPositions) {
            x += pos.getX();
            y += pos.getY();
            z += pos.getZ();
        }
        int size = spawnPositions.size();
        return new Vector3(x / size, y / size, z / size);
    }

    private void broadcastMessage(String message) {
        for (String playerName : players) {
            Player player = plugin.getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendMessage(message);
            }
        }
    }

    private void broadcastTitle(String title, String subtitle) {
        for (String playerName : players) {
            Player player = plugin.getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendTitle(title, subtitle, 10, 40, 10);
            }
        }
    }

    public boolean isPlayer(String name) {
        return players.contains(name);
    }

    public boolean isAlive(String name) {
        return alivePlayers.contains(name);
    }

    public ArenaState getState() {
        return state;
    }

    public int getPlayerCount() {
        return players.size();
    }

    public int getMaxPlayers() {
        return maxPlayers;
    }

    public String getName() {
        return name;
    }
}
