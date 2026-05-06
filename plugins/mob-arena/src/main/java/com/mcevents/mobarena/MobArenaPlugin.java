package com.mcevents.mobarena;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.entity.Entity;
import cn.nukkit.entity.EntityCreature;
import cn.nukkit.level.Position;
import cn.nukkit.nbt.tag.CompoundTag;
import cn.nukkit.nbt.tag.DoubleTag;
import cn.nukkit.nbt.tag.FloatTag;
import cn.nukkit.nbt.tag.ListTag;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.ConfigSection;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class MobArenaPlugin extends PluginBase {

    private boolean arenaActive = false;
    private int currentWave = 0;
    private int totalWaves;
    private int taskId = -1;
    private final Set<String> players = new LinkedHashSet<>();
    private final Set<String> alivePlayers = new HashSet<>();
    private final Map<String, Integer> killCounts = new HashMap<>();
    private final Map<String, Integer> playerLives = new HashMap<>();
    private final List<Entity> spawnedMobs = new ArrayList<>();
    private int mobsAlive = 0;
    private int playerCoins = 0;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        getServer().getPluginManager().registerEvents(new ArenaListener(this), this);
        getLogger().info(TextFormat.GREEN + "MobArena загружен!");
    }

    @Override
    public void onDisable() {
        stopArena();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("ma")) return false;
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
            case "info":
                return handleInfo(sender);
            case "setspawn":
                return handleSetSpawn(sender, args);
            case "setmobspawn":
                return handleSetMobSpawn(sender, args);
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
        if (arenaActive && currentWave > 0) {
            player.sendMessage(msg("arena-in-progress"));
            return true;
        }
        if (players.contains(player.getName())) {
            player.sendMessage(TextFormat.YELLOW + "Вы уже зарегистрированы!");
            return true;
        }
        players.add(player.getName());
        alivePlayers.add(player.getName());
        killCounts.put(player.getName(), 0);
        int lives = getConfig().getInt("settings.player-lives", 3);
        playerLives.put(player.getName(), lives);

        teleportToSpawn(player);
        player.sendMessage(msg("joined").replace("{lives}", String.valueOf(lives)));
        return true;
    }

    private boolean handleLeave(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        removePlayer(player);
        player.sendMessage(msg("left"));
        return true;
    }

    private boolean handleStart(CommandSender sender) {
        if (!sender.hasPermission("ma.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (arenaActive) {
            sender.sendMessage(TextFormat.RED + "Арена уже запущена!");
            return true;
        }
        if (players.isEmpty()) {
            sender.sendMessage(TextFormat.RED + "Нет игроков!");
            return true;
        }
        startArena();
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("ma.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        stopArena();
        sender.sendMessage(TextFormat.GREEN + "Арена остановлена!");
        return true;
    }

    private boolean handleInfo(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== MobArena ===");
        sender.sendMessage(TextFormat.YELLOW + "Статус: " + (arenaActive ? TextFormat.GREEN + "Активна" : TextFormat.RED + "Неактивна"));
        if (arenaActive) {
            sender.sendMessage(TextFormat.YELLOW + "Волна: " + TextFormat.WHITE + currentWave + "/" + totalWaves);
            sender.sendMessage(TextFormat.YELLOW + "Мобы: " + TextFormat.WHITE + mobsAlive);
            sender.sendMessage(TextFormat.YELLOW + "Игроки: " + TextFormat.WHITE + alivePlayers.size());
        }
        return true;
    }

    private boolean handleSetSpawn(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("ma.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        Config config = getConfig();
        config.set("arena.spawn.world", player.getLevel().getName());
        config.set("arena.spawn.x", player.getX());
        config.set("arena.spawn.y", player.getY());
        config.set("arena.spawn.z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Спавн арены установлен!");
        return true;
    }

    private boolean handleSetMobSpawn(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("ma.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/ma setmobspawn <номер>");
            return true;
        }
        Config config = getConfig();
        String path = "arena.mob-spawns." + args[1];
        config.set(path + ".world", player.getLevel().getName());
        config.set(path + ".x", player.getX());
        config.set(path + ".y", player.getY());
        config.set(path + ".z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Точка спавна мобов #" + args[1] + " установлена!");
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("ma.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        sender.sendMessage(TextFormat.GREEN + "MobArena перезагружена!");
        return true;
    }

    private void startArena() {
        arenaActive = true;
        currentWave = 0;
        totalWaves = getConfig().getInt("settings.total-waves", 15);

        broadcastToPlayers(msg("arena-started")
                .replace("{waves}", String.valueOf(totalWaves)));

        startNextWave();
    }

    private void startNextWave() {
        currentWave++;
        if (currentWave > totalWaves) {
            onArenaVictory();
            return;
        }

        boolean isBossWave = getConfig().getIntegerList("settings.boss-waves").contains(currentWave);

        broadcastToPlayers(msg(isBossWave ? "boss-wave" : "wave-started")
                .replace("{wave}", String.valueOf(currentWave))
                .replace("{total}", String.valueOf(totalWaves)));

        for (String playerName : alivePlayers) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendTitle(
                        TextFormat.RED + "ВОЛНА " + currentWave,
                        isBossWave ? TextFormat.DARK_RED + "ВОЛНА БОССА!" : TextFormat.YELLOW + "Приготовьтесь!",
                        10, 40, 10);
            }
        }

        getServer().getScheduler().scheduleDelayedTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                spawnWaveMobs(isBossWave);
            }
        }, 60);
    }

    private void spawnWaveMobs(boolean isBossWave) {
        Config config = getConfig();
        List<Position> mobSpawns = getMobSpawnPositions();
        if (mobSpawns.isEmpty()) {
            broadcastToPlayers(TextFormat.RED + "Ошибка: нет точек спавна мобов!");
            return;
        }

        int baseMobCount = config.getInt("settings.base-mob-count", 5);
        int mobsPerWave = baseMobCount + (currentWave * config.getInt("settings.mobs-increase-per-wave", 2));

        List<String> mobTypes;
        if (isBossWave) {
            mobTypes = config.getStringList("settings.boss-mob-types");
            if (mobTypes.isEmpty()) mobTypes = List.of("Zombie");
            mobsPerWave = config.getInt("settings.boss-mob-count", 3);
        } else {
            mobTypes = getWaveMobTypes();
        }

        Random random = new Random();
        mobsAlive = 0;

        for (int i = 0; i < mobsPerWave; i++) {
            String mobType = mobTypes.get(random.nextInt(mobTypes.size()));
            Position spawnPos = mobSpawns.get(random.nextInt(mobSpawns.size()));

            Entity mob = spawnMob(mobType, spawnPos, isBossWave);
            if (mob != null) {
                spawnedMobs.add(mob);
                mobsAlive++;
            }
        }
    }

    private Entity spawnMob(String entityType, Position pos, boolean isBoss) {
        CompoundTag nbt = new CompoundTag()
                .putList("Pos", new ListTag<DoubleTag>()
                        .add(new DoubleTag(pos.getX()))
                        .add(new DoubleTag(pos.getY()))
                        .add(new DoubleTag(pos.getZ())))
                .putList("Motion", new ListTag<DoubleTag>()
                        .add(new DoubleTag(0))
                        .add(new DoubleTag(0))
                        .add(new DoubleTag(0)))
                .putList("Rotation", new ListTag<FloatTag>()
                        .add(new FloatTag(0))
                        .add(new FloatTag(0)));

        Entity entity = Entity.createEntity(entityType, pos.getLevel().getChunk((int) pos.getX() >> 4, (int) pos.getZ() >> 4), nbt);
        if (entity != null) {
            if (isBoss && entity instanceof EntityCreature creature) {
                float bossHealth = getConfig().getInt("settings.boss-health", 100);
                creature.setMaxHealth((int) bossHealth);
                creature.setHealth(bossHealth);
                entity.setNameTag(TextFormat.DARK_RED + "§l[БОСС] " + entityType);
                entity.setNameTagVisible(true);
                entity.setNameTagAlwaysVisible(true);
            }
            entity.spawnToAll();
        }
        return entity;
    }

    private List<String> getWaveMobTypes() {
        Config config = getConfig();
        if (currentWave <= 5) {
            return config.getStringList("settings.easy-mobs");
        } else if (currentWave <= 10) {
            return config.getStringList("settings.medium-mobs");
        } else {
            return config.getStringList("settings.hard-mobs");
        }
    }

    private List<Position> getMobSpawnPositions() {
        List<Position> positions = new ArrayList<>();
        Config config = getConfig();
        if (!config.exists("arena.mob-spawns")) return positions;

        for (String key : config.getSection("arena.mob-spawns").getKeys(false)) {
            ConfigSection spawn = config.getSection("arena.mob-spawns." + key);
            String worldName = spawn.getString("world", "world");
            cn.nukkit.level.Level level = getServer().getLevelByName(worldName);
            if (level != null) {
                positions.add(new Position(spawn.getDouble("x"), spawn.getDouble("y"), spawn.getDouble("z"), level));
            }
        }
        return positions;
    }

    public void onMobKilled(Player killer, Entity mob) {
        if (!arenaActive) return;

        spawnedMobs.remove(mob);
        mobsAlive--;

        if (killer != null && killCounts.containsKey(killer.getName())) {
            killCounts.merge(killer.getName(), 1, Integer::sum);
            killer.sendMessage(TextFormat.GREEN + "+1 убийство! " + TextFormat.GRAY + "(осталось мобов: " + mobsAlive + ")");
        }

        if (mobsAlive <= 0) {
            broadcastToPlayers(msg("wave-complete").replace("{wave}", String.valueOf(currentWave)));

            int breakTime = getConfig().getInt("settings.break-between-waves", 10);
            broadcastToPlayers(TextFormat.YELLOW + "Следующая волна через " + breakTime + " секунд...");

            taskId = getServer().getScheduler().scheduleDelayedTask(this, new Task() {
                @Override
                public void onRun(int currentTick) {
                    startNextWave();
                }
            }, breakTime * 20).getTaskId();
        }
    }

    public void onPlayerDeath(Player player) {
        int lives = playerLives.getOrDefault(player.getName(), 0) - 1;
        playerLives.put(player.getName(), lives);

        if (lives <= 0) {
            alivePlayers.remove(player.getName());
            player.setGamemode(Player.SPECTATOR);
            player.sendMessage(msg("eliminated"));
            broadcastToPlayers(msg("player-eliminated")
                    .replace("{player}", player.getName())
                    .replace("{remaining}", String.valueOf(alivePlayers.size())));

            if (alivePlayers.isEmpty()) {
                onArenaDefeat();
            }
        } else {
            player.sendMessage(msg("life-lost")
                    .replace("{lives}", String.valueOf(lives)));
            teleportToSpawn(player);
            player.setHealth(player.getMaxHealth());
        }
    }

    private void onArenaVictory() {
        arenaActive = false;
        broadcastToPlayers(msg("arena-victory").replace("{waves}", String.valueOf(totalWaves)));

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(TextFormat.GOLD + "ПОБЕДА!",
                    TextFormat.YELLOW + "Все волны пройдены!", 10, 60, 10);
        }
        broadcastResults();
        resetArena();
    }

    private void onArenaDefeat() {
        arenaActive = false;
        broadcastToPlayers(msg("arena-defeat")
                .replace("{wave}", String.valueOf(currentWave)));
        broadcastResults();
        resetArena();
    }

    private void broadcastResults() {
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(killCounts.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        broadcastToPlayers(TextFormat.GOLD + "=== Результаты MobArena ===");
        broadcastToPlayers(TextFormat.YELLOW + "Пройдено волн: " + currentWave + "/" + totalWaves);
        int rank = 1;
        for (Map.Entry<String, Integer> entry : sorted) {
            if (rank > 10) break;
            broadcastToPlayers(TextFormat.YELLOW + "#" + rank + " " + entry.getKey()
                    + TextFormat.GRAY + " — " + TextFormat.WHITE + entry.getValue() + " убийств");
            rank++;
        }
    }

    public void stopArena() {
        arenaActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        for (Entity mob : spawnedMobs) {
            if (!mob.isClosed()) mob.close();
        }
        resetArena();
    }

    private void resetArena() {
        spawnedMobs.clear();
        mobsAlive = 0;
        for (String playerName : players) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.setGamemode(Player.SURVIVAL);
                player.teleport(getServer().getDefaultLevel().getSpawnLocation());
            }
        }
        players.clear();
        alivePlayers.clear();
        killCounts.clear();
        playerLives.clear();
    }

    private void removePlayer(Player player) {
        players.remove(player.getName());
        alivePlayers.remove(player.getName());
        killCounts.remove(player.getName());
        playerLives.remove(player.getName());
        player.setGamemode(Player.SURVIVAL);
        player.teleport(getServer().getDefaultLevel().getSpawnLocation());
    }

    private void teleportToSpawn(Player player) {
        Config config = getConfig();
        if (config.exists("arena.spawn")) {
            ConfigSection spawn = config.getSection("arena.spawn");
            cn.nukkit.level.Level level = getServer().getLevelByName(spawn.getString("world", "world"));
            if (level != null) {
                player.teleport(new Position(spawn.getDouble("x"), spawn.getDouble("y"), spawn.getDouble("z"), level));
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

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        return TextFormat.colorize(msgConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public boolean isArenaActive() {
        return arenaActive;
    }

    public Set<String> getPlayers() {
        return players;
    }

    public Set<String> getAlivePlayers() {
        return alivePlayers;
    }

    public List<Entity> getSpawnedMobs() {
        return spawnedMobs;
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== MobArena ===");
        sender.sendMessage(TextFormat.YELLOW + "/ma join" + TextFormat.GRAY + " — Присоединиться");
        sender.sendMessage(TextFormat.YELLOW + "/ma leave" + TextFormat.GRAY + " — Покинуть");
        sender.sendMessage(TextFormat.YELLOW + "/ma info" + TextFormat.GRAY + " — Информация");
        if (sender.hasPermission("ma.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/ma start" + TextFormat.GRAY + " — Начать");
            sender.sendMessage(TextFormat.YELLOW + "/ma stop" + TextFormat.GRAY + " — Остановить");
            sender.sendMessage(TextFormat.YELLOW + "/ma setspawn" + TextFormat.GRAY + " — Установить спавн");
            sender.sendMessage(TextFormat.YELLOW + "/ma setmobspawn <номер>" + TextFormat.GRAY + " — Точка спавна мобов");
            sender.sendMessage(TextFormat.YELLOW + "/ma reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
