package com.mcevents.parkourrace;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.level.Position;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.ConfigSection;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class ParkourRacePlugin extends PluginBase {

    private boolean raceActive = false;
    private int raceTimer;
    private int taskId = -1;
    private final Map<String, Integer> playerCheckpoints = new HashMap<>();
    private final Map<String, Long> playerStartTimes = new HashMap<>();
    private final Map<String, Long> playerFinishTimes = new HashMap<>();
    private final Set<String> participants = new LinkedHashSet<>();
    private final List<Position> checkpoints = new ArrayList<>();
    private final List<String> finishOrder = new ArrayList<>();

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        getServer().getPluginManager().registerEvents(new ParkourListener(this), this);
        loadCheckpoints();
        getLogger().info(TextFormat.GREEN + "ParkourRace загружен! Чекпоинтов: " + checkpoints.size());
    }

    @Override
    public void onDisable() {
        stopRace();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("parkour")) return false;
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
            case "addcp":
                return handleAddCheckpoint(sender, args);
            case "setstart":
                return handleSetStart(sender);
            case "setfinish":
                return handleSetFinish(sender);
            case "top":
                return handleTop(sender);
            case "time":
                return handleTime(sender);
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
        if (!raceActive) {
            player.sendMessage(msg("race-not-active"));
            return true;
        }
        if (participants.contains(player.getName())) {
            player.sendMessage(TextFormat.YELLOW + "Вы уже участвуете!");
            return true;
        }
        participants.add(player.getName());
        playerCheckpoints.put(player.getName(), 0);
        playerStartTimes.put(player.getName(), System.currentTimeMillis());

        teleportToStart(player);
        player.sendMessage(msg("joined")
                .replace("{checkpoints}", String.valueOf(checkpoints.size())));
        return true;
    }

    private boolean handleLeave(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        participants.remove(player.getName());
        playerCheckpoints.remove(player.getName());
        player.sendMessage(msg("left"));
        player.teleport(getServer().getDefaultLevel().getSpawnLocation());
        return true;
    }

    private boolean handleStart(CommandSender sender) {
        if (!sender.hasPermission("parkour.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (raceActive) {
            sender.sendMessage(TextFormat.RED + "Гонка уже идёт!");
            return true;
        }
        if (checkpoints.isEmpty()) {
            sender.sendMessage(TextFormat.RED + "Нет чекпоинтов! Добавьте через /parkour addcp");
            return true;
        }
        startRace();
        sender.sendMessage(TextFormat.GREEN + "Паркур-гонка запущена!");
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("parkour.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        stopRace();
        sender.sendMessage(TextFormat.GREEN + "Гонка остановлена!");
        return true;
    }

    private boolean handleAddCheckpoint(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("parkour.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        int index = checkpoints.size() + 1;
        if (args.length >= 2) {
            try {
                index = Integer.parseInt(args[1]);
            } catch (NumberFormatException ignored) {
            }
        }
        Config config = getConfig();
        String path = "checkpoints." + index;
        config.set(path + ".world", player.getLevel().getName());
        config.set(path + ".x", player.getX());
        config.set(path + ".y", player.getY());
        config.set(path + ".z", player.getZ());
        config.save();
        loadCheckpoints();
        player.sendMessage(TextFormat.GREEN + "Чекпоинт #" + index + " добавлен! Всего: " + checkpoints.size());
        return true;
    }

    private boolean handleSetStart(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("parkour.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        Config config = getConfig();
        config.set("start.world", player.getLevel().getName());
        config.set("start.x", player.getX());
        config.set("start.y", player.getY());
        config.set("start.z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Стартовая позиция установлена!");
        return true;
    }

    private boolean handleSetFinish(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("parkour.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        Config config = getConfig();
        config.set("finish.world", player.getLevel().getName());
        config.set("finish.x", player.getX());
        config.set("finish.y", player.getY());
        config.set("finish.z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Финишная позиция установлена!");
        return true;
    }

    private boolean handleTop(CommandSender sender) {
        Config config = new Config(getDataFolder() + "/records.yml", Config.YAML);
        if (config.getKeys(false).isEmpty()) {
            sender.sendMessage(TextFormat.YELLOW + "Нет рекордов.");
            return true;
        }

        sender.sendMessage(TextFormat.GOLD + "=== Рекорды паркура ===");
        List<Map.Entry<String, Object>> records = new ArrayList<>();
        for (String key : config.getKeys(false)) {
            records.add(Map.entry(key, config.get(key)));
        }
        records.sort((a, b) -> Long.compare(((Number) a.getValue()).longValue(), ((Number) b.getValue()).longValue()));

        int rank = 1;
        for (Map.Entry<String, Object> entry : records) {
            if (rank > 10) break;
            long time = ((Number) entry.getValue()).longValue();
            sender.sendMessage(TextFormat.YELLOW + "#" + rank + " " + entry.getKey()
                    + TextFormat.GRAY + " — " + TextFormat.WHITE + formatTime(time));
            rank++;
        }
        return true;
    }

    private boolean handleTime(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!participants.contains(player.getName())) {
            player.sendMessage(TextFormat.RED + "Вы не участвуете в гонке!");
            return true;
        }
        long startTime = playerStartTimes.getOrDefault(player.getName(), System.currentTimeMillis());
        long elapsed = System.currentTimeMillis() - startTime;
        int cp = playerCheckpoints.getOrDefault(player.getName(), 0);
        player.sendMessage(TextFormat.YELLOW + "Время: " + TextFormat.WHITE + formatTime(elapsed)
                + TextFormat.YELLOW + " | Чекпоинты: " + TextFormat.WHITE + cp + "/" + checkpoints.size());
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("parkour.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        loadCheckpoints();
        sender.sendMessage(TextFormat.GREEN + "ParkourRace перезагружен!");
        return true;
    }

    private void startRace() {
        raceActive = true;
        participants.clear();
        playerCheckpoints.clear();
        playerStartTimes.clear();
        playerFinishTimes.clear();
        finishOrder.clear();
        raceTimer = getConfig().getInt("settings.race-duration", 600);

        getServer().broadcastMessage(msg("race-started")
                .replace("{time}", String.valueOf(raceTimer / 60))
                .replace("{checkpoints}", String.valueOf(checkpoints.size())));

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(TextFormat.GREEN + "ПАРКУР-ГОНКА!",
                    TextFormat.YELLOW + "/parkour join", 10, 60, 10);
        }

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (raceTimer <= 0) {
                    endRace();
                    this.getHandler().cancel();
                    return;
                }
                if (raceTimer == 60 || raceTimer == 30 || raceTimer == 10) {
                    broadcastToParticipants(msg("time-remaining")
                            .replace("{time}", String.valueOf(raceTimer)));
                }
                raceTimer--;
            }
        }, 20).getTaskId();
    }

    public void onPlayerReachCheckpoint(Player player, int checkpointIndex) {
        if (!raceActive) return;
        if (!participants.contains(player.getName())) return;

        int current = playerCheckpoints.getOrDefault(player.getName(), 0);
        if (checkpointIndex != current + 1) return;

        playerCheckpoints.put(player.getName(), checkpointIndex);
        long elapsed = System.currentTimeMillis() - playerStartTimes.getOrDefault(player.getName(), System.currentTimeMillis());

        player.sendMessage(msg("checkpoint-reached")
                .replace("{cp}", String.valueOf(checkpointIndex))
                .replace("{total}", String.valueOf(checkpoints.size()))
                .replace("{time}", formatTime(elapsed)));

        player.sendTitle("", TextFormat.GREEN + "Чекпоинт " + checkpointIndex + "/" + checkpoints.size(), 5, 20, 5);
    }

    public void onPlayerFinish(Player player) {
        if (!raceActive) return;
        if (!participants.contains(player.getName())) return;
        if (finishOrder.contains(player.getName())) return;

        int requiredCheckpoints = checkpoints.size();
        int playerCp = playerCheckpoints.getOrDefault(player.getName(), 0);
        if (playerCp < requiredCheckpoints) {
            player.sendMessage(TextFormat.RED + "Пройдите все чекпоинты! (" + playerCp + "/" + requiredCheckpoints + ")");
            return;
        }

        long elapsed = System.currentTimeMillis() - playerStartTimes.getOrDefault(player.getName(), System.currentTimeMillis());
        playerFinishTimes.put(player.getName(), elapsed);
        finishOrder.add(player.getName());

        int place = finishOrder.size();
        broadcastToParticipants(msg("player-finished")
                .replace("{player}", player.getName())
                .replace("{place}", String.valueOf(place))
                .replace("{time}", formatTime(elapsed)));

        player.sendTitle(TextFormat.GOLD + "#" + place, TextFormat.YELLOW + formatTime(elapsed), 10, 40, 10);

        saveRecord(player.getName(), elapsed);
    }

    private void endRace() {
        raceActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        getServer().broadcastMessage(msg("race-ended"));

        if (!finishOrder.isEmpty()) {
            getServer().broadcastMessage(TextFormat.GOLD + "=== Результаты паркур-гонки ===");
            int rank = 1;
            for (String playerName : finishOrder) {
                long time = playerFinishTimes.getOrDefault(playerName, 0L);
                String medal = rank == 1 ? "§6★" : rank == 2 ? "§7★" : rank == 3 ? "§c★" : "§7 ";
                getServer().broadcastMessage(medal + " #" + rank + " " + playerName
                        + " §7— §e" + formatTime(time));
                rank++;
                if (rank > 10) break;
            }
        }

        participants.clear();
    }

    public void stopRace() {
        raceActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        participants.clear();
    }

    private void loadCheckpoints() {
        checkpoints.clear();
        Config config = getConfig();
        if (!config.exists("checkpoints")) return;

        TreeMap<Integer, Position> sorted = new TreeMap<>();
        for (String key : config.getSection("checkpoints").getKeys(false)) {
            ConfigSection cp = config.getSection("checkpoints." + key);
            cn.nukkit.level.Level level = getServer().getLevelByName(cp.getString("world", "world"));
            if (level != null) {
                sorted.put(Integer.parseInt(key),
                        new Position(cp.getDouble("x"), cp.getDouble("y"), cp.getDouble("z"), level));
            }
        }
        checkpoints.addAll(sorted.values());
    }

    private void teleportToStart(Player player) {
        Config config = getConfig();
        if (config.exists("start")) {
            cn.nukkit.level.Level level = getServer().getLevelByName(config.getString("start.world", "world"));
            if (level != null) {
                player.teleport(new Position(
                        config.getDouble("start.x"), config.getDouble("start.y"),
                        config.getDouble("start.z"), level));
            }
        }
    }

    private void saveRecord(String playerName, long time) {
        Config records = new Config(getDataFolder() + "/records.yml", Config.YAML);
        long existing = records.getLong(playerName, Long.MAX_VALUE);
        if (time < existing) {
            records.set(playerName, time);
            records.save();
        }
    }

    private void broadcastToParticipants(String message) {
        for (String playerName : participants) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendMessage(message);
            }
        }
    }

    private String formatTime(long millis) {
        long seconds = millis / 1000;
        long ms = millis % 1000;
        long min = seconds / 60;
        long sec = seconds % 60;
        return String.format("%d:%02d.%03d", min, sec, ms);
    }

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        return TextFormat.colorize(msgConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public boolean isRaceActive() {
        return raceActive;
    }

    public List<Position> getCheckpoints() {
        return checkpoints;
    }

    public Set<String> getParticipants() {
        return participants;
    }

    public Position getFinishPosition() {
        Config config = getConfig();
        if (!config.exists("finish")) return null;
        cn.nukkit.level.Level level = getServer().getLevelByName(config.getString("finish.world", "world"));
        if (level == null) return null;
        return new Position(config.getDouble("finish.x"), config.getDouble("finish.y"),
                config.getDouble("finish.z"), level);
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== ParkourRace ===");
        sender.sendMessage(TextFormat.YELLOW + "/parkour join" + TextFormat.GRAY + " — Присоединиться");
        sender.sendMessage(TextFormat.YELLOW + "/parkour leave" + TextFormat.GRAY + " — Покинуть");
        sender.sendMessage(TextFormat.YELLOW + "/parkour time" + TextFormat.GRAY + " — Ваше время");
        sender.sendMessage(TextFormat.YELLOW + "/parkour top" + TextFormat.GRAY + " — Рекорды");
        if (sender.hasPermission("parkour.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/parkour start" + TextFormat.GRAY + " — Начать гонку");
            sender.sendMessage(TextFormat.YELLOW + "/parkour stop" + TextFormat.GRAY + " — Остановить");
            sender.sendMessage(TextFormat.YELLOW + "/parkour setstart" + TextFormat.GRAY + " — Установить старт");
            sender.sendMessage(TextFormat.YELLOW + "/parkour setfinish" + TextFormat.GRAY + " — Установить финиш");
            sender.sendMessage(TextFormat.YELLOW + "/parkour addcp [номер]" + TextFormat.GRAY + " — Добавить чекпоинт");
            sender.sendMessage(TextFormat.YELLOW + "/parkour reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
