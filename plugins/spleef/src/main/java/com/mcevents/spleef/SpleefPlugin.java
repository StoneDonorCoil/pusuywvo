package com.mcevents.spleef;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.item.Item;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class SpleefPlugin extends PluginBase {

    public enum GameState {
        WAITING, COUNTDOWN, INGAME, ENDED
    }

    private GameState state = GameState.WAITING;
    private final Set<String> players = new LinkedHashSet<>();
    private final Set<String> alivePlayers = new HashSet<>();
    private int taskId = -1;
    private int timer;
    private double fallLevel;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        getServer().getPluginManager().registerEvents(new SpleefListener(this), this);
        getLogger().info(TextFormat.GREEN + "Spleef загружен!");
    }

    @Override
    public void onDisable() {
        forceStop();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("spleef")) return false;
        if (args.length == 0) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "join":
                return handleJoin(sender);
            case "leave":
                return handleLeave(sender);
            case "start":
                return handleStart(sender);
            case "stop":
                return handleStop(sender);
            case "setspawn":
                return handleSetSpawn(sender);
            case "setfall":
                return handleSetFall(sender);
            case "reload":
                return handleReload(sender);
            default:
                sendHelp(sender);
                return true;
        }
    }

    private boolean handleJoin(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (state == GameState.INGAME) {
            player.sendMessage(msg("game-in-progress"));
            return true;
        }
        if (players.contains(player.getName())) {
            player.sendMessage(TextFormat.YELLOW + "Вы уже в игре!");
            return true;
        }
        int maxPlayers = getConfig().getInt("settings.max-players", 16);
        if (players.size() >= maxPlayers) {
            player.sendMessage(msg("game-full"));
            return true;
        }

        players.add(player.getName());
        alivePlayers.add(player.getName());
        teleportToArena(player);
        player.getInventory().clearAll();
        player.setGamemode(Player.ADVENTURE);

        broadcastToPlayers(msg("player-joined")
                .replace("{player}", player.getName())
                .replace("{count}", String.valueOf(players.size()))
                .replace("{max}", String.valueOf(maxPlayers)));

        int minPlayers = getConfig().getInt("settings.min-players", 2);
        if (players.size() >= minPlayers && state == GameState.WAITING) {
            startCountdown();
        }
        return true;
    }

    private boolean handleLeave(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        removePlayer(player);
        return true;
    }

    private boolean handleStart(CommandSender sender) {
        if (!sender.hasPermission("spleef.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (state == GameState.INGAME) {
            sender.sendMessage(TextFormat.RED + "Игра уже идёт!");
            return true;
        }
        if (players.size() < 2) {
            sender.sendMessage(TextFormat.RED + "Нужно минимум 2 игрока!");
            return true;
        }
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
        }
        startGame();
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("spleef.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        forceStop();
        sender.sendMessage(TextFormat.GREEN + "Spleef остановлен!");
        return true;
    }

    private boolean handleSetSpawn(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("spleef.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        Config config = getConfig();
        config.set("arena.spawn.world", player.getLevel().getName());
        config.set("arena.spawn.x", player.getX());
        config.set("arena.spawn.y", player.getY());
        config.set("arena.spawn.z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Спавн Spleef установлен!");
        return true;
    }

    private boolean handleSetFall(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("spleef.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        Config config = getConfig();
        config.set("arena.fall-level", player.getY());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Уровень падения установлен на Y=" + String.format("%.1f", player.getY()));
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("spleef.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        sender.sendMessage(TextFormat.GREEN + "Spleef перезагружен!");
        return true;
    }

    private void startCountdown() {
        state = GameState.COUNTDOWN;
        timer = getConfig().getInt("settings.countdown", 15);

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (timer <= 0) {
                    startGame();
                    this.getHandler().cancel();
                    return;
                }
                if (timer <= 5 || timer == 10) {
                    broadcastToPlayers(msg("countdown")
                            .replace("{seconds}", String.valueOf(timer)));
                }
                timer--;
            }
        }, 20).getTaskId();
    }

    private void startGame() {
        state = GameState.INGAME;
        fallLevel = getConfig().getDouble("arena.fall-level", 50.0);
        timer = getConfig().getInt("settings.game-time", 300);

        for (String playerName : players) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.setGamemode(Player.SURVIVAL);
                Item shovel = Item.get(Item.DIAMOND_SHOVEL, 0, 1);
                player.getInventory().clearAll();
                player.getInventory().addItem(shovel);

                if (getConfig().getBoolean("settings.give-snowballs", true)) {
                    player.getInventory().addItem(Item.get(Item.SNOWBALL, 0, 16));
                }
            }
        }

        broadcastToPlayers(msg("game-started"));
        broadcastTitle(TextFormat.AQUA + "SPLEEF!", TextFormat.YELLOW + "Ломайте блоки под ногами!");

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (timer <= 0 || alivePlayers.size() <= 1) {
                    endGame();
                    this.getHandler().cancel();
                    return;
                }
                checkFallenPlayers();
                if (timer == 60 || timer == 30 || timer == 10) {
                    broadcastToPlayers(msg("time-left")
                            .replace("{time}", String.valueOf(timer)));
                }
                timer--;
            }
        }, 20).getTaskId();
    }

    public void checkFallenPlayers() {
        for (String playerName : new HashSet<>(alivePlayers)) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null && player.getY() < fallLevel) {
                eliminatePlayer(player);
            }
        }
    }

    public void eliminatePlayer(Player player) {
        if (!alivePlayers.contains(player.getName())) return;
        alivePlayers.remove(player.getName());
        player.setGamemode(Player.SPECTATOR);
        player.getInventory().clearAll();

        broadcastToPlayers(msg("player-eliminated")
                .replace("{player}", player.getName())
                .replace("{remaining}", String.valueOf(alivePlayers.size())));

        if (alivePlayers.size() <= 1) {
            endGame();
        }
    }

    private void endGame() {
        state = GameState.ENDED;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        if (alivePlayers.size() == 1) {
            String winner = alivePlayers.iterator().next();
            broadcastToPlayers(msg("winner").replace("{player}", winner));
            broadcastTitle(TextFormat.GOLD + "ПОБЕДИТЕЛЬ!", TextFormat.YELLOW + winner);
        } else {
            broadcastToPlayers(msg("draw"));
        }

        getServer().getScheduler().scheduleDelayedTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                resetGame();
            }
        }, 100);
    }

    private void removePlayer(Player player) {
        players.remove(player.getName());
        alivePlayers.remove(player.getName());
        player.getInventory().clearAll();
        player.setGamemode(Player.SURVIVAL);
        player.teleport(getServer().getDefaultLevel().getSpawnLocation());
        player.sendMessage(msg("left"));

        if (state == GameState.INGAME && alivePlayers.size() <= 1) {
            endGame();
        }
        if (state == GameState.COUNTDOWN && players.size() < getConfig().getInt("settings.min-players", 2)) {
            if (taskId != -1) {
                getServer().getScheduler().cancelTask(taskId);
                taskId = -1;
            }
            state = GameState.WAITING;
            broadcastToPlayers(TextFormat.RED + "Недостаточно игроков! Отсчёт отменён.");
        }
    }

    public void forceStop() {
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        resetGame();
    }

    private void resetGame() {
        for (String playerName : players) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.getInventory().clearAll();
                player.setGamemode(Player.SURVIVAL);
                player.teleport(getServer().getDefaultLevel().getSpawnLocation());
            }
        }
        players.clear();
        alivePlayers.clear();
        state = GameState.WAITING;
    }

    private void teleportToArena(Player player) {
        Config config = getConfig();
        if (config.exists("arena.spawn")) {
            cn.nukkit.utils.ConfigSection spawn = config.getSection("arena.spawn");
            cn.nukkit.level.Level level = getServer().getLevelByName(spawn.getString("world", "world"));
            if (level != null) {
                player.teleport(new cn.nukkit.level.Position(spawn.getDouble("x"), spawn.getDouble("y"), spawn.getDouble("z"), level));
            }
        }
    }

    private void broadcastToPlayers(String message) {
        for (String playerName : players) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendMessage(message);
            }
        }
    }

    private void broadcastTitle(String title, String subtitle) {
        for (String playerName : players) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendTitle(title, subtitle, 10, 40, 10);
            }
        }
    }

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        return TextFormat.colorize(msgConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public GameState getState() {
        return state;
    }

    public Set<String> getGamePlayers() {
        return players;
    }

    public Set<String> getAlivePlayers() {
        return alivePlayers;
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== Spleef ===");
        sender.sendMessage(TextFormat.YELLOW + "/spleef join" + TextFormat.GRAY + " — Присоединиться");
        sender.sendMessage(TextFormat.YELLOW + "/spleef leave" + TextFormat.GRAY + " — Покинуть");
        if (sender.hasPermission("spleef.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/spleef start" + TextFormat.GRAY + " — Начать");
            sender.sendMessage(TextFormat.YELLOW + "/spleef stop" + TextFormat.GRAY + " — Остановить");
            sender.sendMessage(TextFormat.YELLOW + "/spleef setspawn" + TextFormat.GRAY + " — Установить спавн");
            sender.sendMessage(TextFormat.YELLOW + "/spleef setfall" + TextFormat.GRAY + " — Установить уровень падения");
            sender.sendMessage(TextFormat.YELLOW + "/spleef reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
