package com.mcevents.bossraid;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.entity.Entity;
import cn.nukkit.entity.EntityCreature;
import cn.nukkit.level.Level;
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

public class BossRaidPlugin extends PluginBase {

    private final Map<String, Double> playerDamage = new HashMap<>();
    private final Set<String> participants = new HashSet<>();
    private boolean raidActive = false;
    private Entity bossEntity;
    private double bossMaxHealth;
    private double bossCurrentHealth;
    private int currentPhase = 0;
    private int raidTimer;
    private int taskId = -1;
    private String currentBossType;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        getServer().getPluginManager().registerEvents(new BossListener(this), this);
        getLogger().info(TextFormat.GREEN + "BossRaid загружен!");
    }

    @Override
    public void onDisable() {
        if (raidActive) {
            stopRaid(true);
        }
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("boss")) return false;

        if (args.length == 0) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "start":
                return handleStart(sender, args);
            case "stop":
                return handleStop(sender);
            case "join":
                return handleJoin(sender);
            case "info":
                return handleInfo(sender);
            case "top":
                return handleTop(sender);
            case "setspawn":
                return handleSetSpawn(sender, args);
            case "list":
                return handleListBosses(sender);
            case "reload":
                return handleReload(sender);
            default:
                sendHelp(sender);
                return true;
        }
    }

    private boolean handleStart(CommandSender sender, String[] args) {
        if (!sender.hasPermission("boss.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (raidActive) {
            sender.sendMessage(TextFormat.RED + "Рейд уже идёт!");
            return true;
        }
        if (args.length < 2) {
            sender.sendMessage(TextFormat.RED + "/boss start <тип_босса>");
            return true;
        }
        String bossType = args[1].toLowerCase();
        Config config = getConfig();
        if (!config.exists("bosses." + bossType)) {
            sender.sendMessage(TextFormat.RED + "Тип босса '" + bossType + "' не найден! Используйте /boss list");
            return true;
        }
        startRaid(bossType);
        sender.sendMessage(TextFormat.GREEN + "Рейд на босса '" + bossType + "' запущен!");
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("boss.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (!raidActive) {
            sender.sendMessage(TextFormat.RED + "Рейд не активен!");
            return true;
        }
        stopRaid(true);
        sender.sendMessage(TextFormat.GREEN + "Рейд остановлен!");
        return true;
    }

    private boolean handleJoin(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!raidActive) {
            player.sendMessage(msg("raid-not-active"));
            return true;
        }
        if (participants.contains(player.getName())) {
            player.sendMessage(TextFormat.YELLOW + "Вы уже участвуете в рейде!");
            return true;
        }
        participants.add(player.getName());
        playerDamage.put(player.getName(), 0.0);

        Config config = getConfig();
        if (config.exists("bosses." + currentBossType + ".spawn")) {
            ConfigSection spawnSection = config.getSection("bosses." + currentBossType + ".spawn");
            String worldName = spawnSection.getString("world", "world");
            Level level = getServer().getLevelByName(worldName);
            if (level != null) {
                player.teleport(new Position(
                        spawnSection.getDouble("x"),
                        spawnSection.getDouble("y"),
                        spawnSection.getDouble("z"),
                        level));
            }
        }

        player.sendMessage(msg("joined-raid"));
        broadcastToParticipants(msg("player-joined-raid")
                .replace("{player}", player.getName())
                .replace("{count}", String.valueOf(participants.size())));
        return true;
    }

    private boolean handleInfo(CommandSender sender) {
        if (!raidActive) {
            sender.sendMessage(msg("raid-not-active"));
            return true;
        }
        double healthPercent = (bossCurrentHealth / bossMaxHealth) * 100;
        sender.sendMessage(TextFormat.GOLD + "=== Рейд на Босса ===");
        sender.sendMessage(TextFormat.YELLOW + "Босс: " + TextFormat.WHITE + currentBossType);
        sender.sendMessage(TextFormat.YELLOW + "HP: " + getHealthBar(healthPercent)
                + TextFormat.WHITE + String.format(" %.0f/%.0f (%.1f%%)", bossCurrentHealth, bossMaxHealth, healthPercent));
        sender.sendMessage(TextFormat.YELLOW + "Фаза: " + TextFormat.WHITE + currentPhase);
        sender.sendMessage(TextFormat.YELLOW + "Участники: " + TextFormat.WHITE + participants.size());
        sender.sendMessage(TextFormat.YELLOW + "Осталось: " + TextFormat.WHITE + formatTime(raidTimer));

        if (sender instanceof Player player && participants.contains(player.getName())) {
            double dmg = playerDamage.getOrDefault(player.getName(), 0.0);
            sender.sendMessage(TextFormat.YELLOW + "Ваш урон: " + TextFormat.WHITE + String.format("%.1f", dmg));
        }
        return true;
    }

    private boolean handleTop(CommandSender sender) {
        if (playerDamage.isEmpty()) {
            sender.sendMessage(TextFormat.YELLOW + "Нет данных о уроне.");
            return true;
        }
        List<Map.Entry<String, Double>> sorted = new ArrayList<>(playerDamage.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        sender.sendMessage(TextFormat.GOLD + "=== Топ урона ===");
        int rank = 1;
        for (Map.Entry<String, Double> entry : sorted) {
            if (rank > 10) break;
            double percent = bossMaxHealth > 0 ? (entry.getValue() / bossMaxHealth) * 100 : 0;
            sender.sendMessage(TextFormat.YELLOW + "#" + rank + " " + entry.getKey()
                    + TextFormat.GRAY + " — " + TextFormat.WHITE + String.format("%.1f урона (%.1f%%)", entry.getValue(), percent));
            rank++;
        }
        return true;
    }

    private boolean handleSetSpawn(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("boss.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/boss setspawn <тип_босса>");
            return true;
        }
        String bossType = args[1].toLowerCase();
        Config config = getConfig();
        String path = "bosses." + bossType + ".spawn";
        config.set(path + ".world", player.getLevel().getName());
        config.set(path + ".x", player.getX());
        config.set(path + ".y", player.getY());
        config.set(path + ".z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Точка спавна босса '" + bossType + "' установлена!");
        return true;
    }

    private boolean handleListBosses(CommandSender sender) {
        Config config = getConfig();
        if (!config.exists("bosses")) {
            sender.sendMessage(TextFormat.YELLOW + "Нет настроенных боссов.");
            return true;
        }
        sender.sendMessage(TextFormat.GOLD + "=== Типы боссов ===");
        for (String bossType : config.getSection("bosses").getKeys(false)) {
            ConfigSection bossSection = config.getSection("bosses." + bossType);
            sender.sendMessage(TextFormat.YELLOW + "  " + bossType
                    + TextFormat.GRAY + " | HP: " + bossSection.getDouble("max-health", 500)
                    + " | Фаз: " + bossSection.getInt("phases", 3)
                    + " | Моб: " + bossSection.getString("entity-type", "Zombie"));
        }
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("boss.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        sender.sendMessage(TextFormat.GREEN + "BossRaid перезагружен!");
        return true;
    }

    private void startRaid(String bossType) {
        raidActive = true;
        currentBossType = bossType;
        currentPhase = 1;
        playerDamage.clear();
        participants.clear();

        Config config = getConfig();
        ConfigSection bossConfig = config.getSection("bosses." + bossType);
        bossMaxHealth = bossConfig.getDouble("max-health", 500);
        bossCurrentHealth = bossMaxHealth;
        raidTimer = bossConfig.getInt("time-limit", 600);

        spawnBossEntity(bossType, bossConfig);

        String announcement = msg("raid-started")
                .replace("{boss}", bossType)
                .replace("{health}", String.format("%.0f", bossMaxHealth))
                .replace("{time}", formatTime(raidTimer));
        getServer().broadcastMessage(announcement);

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(
                    TextFormat.DARK_RED + "РЕЙД НА БОССА!",
                    TextFormat.RED + "Используй /boss join",
                    10, 60, 10);
        }

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (!raidActive) {
                    this.getHandler().cancel();
                    return;
                }
                if (raidTimer <= 0) {
                    broadcastToParticipants(msg("raid-timeout"));
                    stopRaid(false);
                    this.getHandler().cancel();
                    return;
                }
                if (raidTimer == 60 || raidTimer == 30 || raidTimer == 10) {
                    broadcastToParticipants(msg("time-remaining")
                            .replace("{time}", formatTime(raidTimer)));
                }
                updateBossBar();
                raidTimer--;
            }
        }, 20).getTaskId();
    }

    private void spawnBossEntity(String bossType, ConfigSection bossConfig) {
        String entityType = bossConfig.getString("entity-type", "Zombie");
        if (!bossConfig.exists("spawn")) return;

        ConfigSection spawnSection = bossConfig.getSection("spawn");
        String worldName = spawnSection.getString("world", "world");
        Level level = getServer().getLevelByName(worldName);
        if (level == null) return;

        double x = spawnSection.getDouble("x");
        double y = spawnSection.getDouble("y");
        double z = spawnSection.getDouble("z");

        CompoundTag nbt = new CompoundTag()
                .putList("Pos", new ListTag<DoubleTag>()
                        .add(new DoubleTag(x))
                        .add(new DoubleTag(y))
                        .add(new DoubleTag(z)))
                .putList("Motion", new ListTag<DoubleTag>()
                        .add(new DoubleTag(0))
                        .add(new DoubleTag(0))
                        .add(new DoubleTag(0)))
                .putList("Rotation", new ListTag<FloatTag>()
                        .add(new FloatTag(0))
                        .add(new FloatTag(0)));

        bossEntity = Entity.createEntity(entityType, level.getChunk((int) x >> 4, (int) z >> 4), nbt);
        if (bossEntity != null) {
            bossEntity.setNameTag(TextFormat.DARK_RED + "§l" + bossConfig.getString("display-name", bossType));
            bossEntity.setNameTagVisible(true);
            bossEntity.setNameTagAlwaysVisible(true);
            if (bossEntity instanceof EntityCreature creature) {
                creature.setMaxHealth((int) bossMaxHealth);
                creature.setHealth((float) bossMaxHealth);
            }
            bossEntity.spawnToAll();
        }
    }

    public void onBossDamage(Player attacker, double damage) {
        if (!raidActive) return;
        if (!participants.contains(attacker.getName())) {
            participants.add(attacker.getName());
            playerDamage.put(attacker.getName(), 0.0);
        }

        playerDamage.merge(attacker.getName(), damage, Double::sum);
        bossCurrentHealth -= damage;

        if (bossCurrentHealth <= 0) {
            bossCurrentHealth = 0;
            onBossDefeated();
            return;
        }

        Config config = getConfig();
        int totalPhases = config.getInt("bosses." + currentBossType + ".phases", 3);
        int newPhase = totalPhases - (int) ((bossCurrentHealth / bossMaxHealth) * totalPhases);
        if (newPhase < 1) newPhase = 1;

        if (newPhase > currentPhase) {
            currentPhase = newPhase;
            onPhaseChange();
        }
    }

    private void onPhaseChange() {
        broadcastToParticipants(msg("phase-change")
                .replace("{phase}", String.valueOf(currentPhase)));

        for (String playerName : participants) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendTitle("",
                        TextFormat.RED + "Фаза " + currentPhase + "!",
                        5, 30, 5);
            }
        }
    }

    private void onBossDefeated() {
        raidActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        getServer().broadcastMessage(msg("boss-defeated")
                .replace("{boss}", currentBossType));

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(
                    TextFormat.GOLD + "БОСС ПОВЕРЖЕН!",
                    TextFormat.YELLOW + "Поздравляем!",
                    10, 60, 10);
        }

        distributeRewards();

        if (bossEntity != null && !bossEntity.isClosed()) {
            bossEntity.close();
        }
    }

    private void distributeRewards() {
        if (playerDamage.isEmpty()) return;

        List<Map.Entry<String, Double>> sorted = new ArrayList<>(playerDamage.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        getServer().broadcastMessage(TextFormat.GOLD + "=== Результаты рейда ===");

        Config config = getConfig();
        int baseMoney = config.getInt("bosses." + currentBossType + ".rewards.base-money", 200);
        int topBonus = config.getInt("bosses." + currentBossType + ".rewards.top-bonus", 500);

        int rank = 1;
        for (Map.Entry<String, Double> entry : sorted) {
            double percent = (entry.getValue() / bossMaxHealth) * 100;
            Player player = getServer().getPlayerExact(entry.getKey());

            int reward = baseMoney + (int) (percent * 5);
            if (rank <= 3) {
                reward += topBonus / rank;
            }

            String medal = rank <= 3 ? (rank == 1 ? "§6★" : rank == 2 ? "§7★" : "§c★") : "§7 ";
            getServer().broadcastMessage(medal + " #" + rank + " " + entry.getKey()
                    + " §7— §e" + String.format("%.1f урона (%.1f%%)", entry.getValue(), percent));

            if (player != null) {
                player.sendMessage(TextFormat.GREEN + "Награда за рейд: +" + reward + " монет!");
            }
            rank++;
            if (rank > 10) break;
        }
    }

    public void stopRaid(boolean force) {
        raidActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        if (bossEntity != null && !bossEntity.isClosed()) {
            bossEntity.close();
        }
        if (force) {
            getServer().broadcastMessage(msg("raid-stopped"));
        }
        participants.clear();
    }

    private void updateBossBar() {
        if (bossEntity == null || bossEntity.isClosed()) return;
        double healthPercent = (bossCurrentHealth / bossMaxHealth) * 100;
        String healthBar = getHealthBar(healthPercent);
        bossEntity.setNameTag(TextFormat.DARK_RED + "§l" + currentBossType
                + "\n" + healthBar + TextFormat.WHITE + String.format(" %.0f/%.0f", bossCurrentHealth, bossMaxHealth));
    }

    private String getHealthBar(double percent) {
        StringBuilder bar = new StringBuilder("§8[");
        int filled = (int) (percent / 5);
        for (int i = 0; i < 20; i++) {
            bar.append(i < filled ? "§a|" : "§c|");
        }
        bar.append("§8]");
        return bar.toString();
    }

    private void broadcastToParticipants(String message) {
        for (String playerName : participants) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendMessage(message);
            }
        }
    }

    private String formatTime(int seconds) {
        int min = seconds / 60;
        int sec = seconds % 60;
        return String.format("%d:%02d", min, sec);
    }

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        return TextFormat.colorize(msgConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public boolean isRaidActive() {
        return raidActive;
    }

    public Entity getBossEntity() {
        return bossEntity;
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== BossRaid ===");
        sender.sendMessage(TextFormat.YELLOW + "/boss join" + TextFormat.GRAY + " — Присоединиться к рейду");
        sender.sendMessage(TextFormat.YELLOW + "/boss info" + TextFormat.GRAY + " — Информация о рейде");
        sender.sendMessage(TextFormat.YELLOW + "/boss top" + TextFormat.GRAY + " — Топ урона");
        if (sender.hasPermission("boss.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/boss start <тип>" + TextFormat.GRAY + " — Запустить рейд");
            sender.sendMessage(TextFormat.YELLOW + "/boss stop" + TextFormat.GRAY + " — Остановить рейд");
            sender.sendMessage(TextFormat.YELLOW + "/boss setspawn <тип>" + TextFormat.GRAY + " — Установить спавн босса");
            sender.sendMessage(TextFormat.YELLOW + "/boss list" + TextFormat.GRAY + " — Список типов боссов");
            sender.sendMessage(TextFormat.YELLOW + "/boss reload" + TextFormat.GRAY + " — Перезагрузить конфиг");
        }
    }
}
