package com.mcevents.kingofthehill;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class KothPlugin extends PluginBase {

    private boolean eventActive = false;
    private int eventTimer;
    private int taskId = -1;
    private final Map<String, Integer> scores = new HashMap<>();
    private final Set<String> participants = new HashSet<>();
    private String currentKing = null;

    private double zoneX1, zoneY1, zoneZ1;
    private double zoneX2, zoneY2, zoneZ2;
    private String zoneWorld;
    private int pointsToWin;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        getServer().getPluginManager().registerEvents(new KothListener(this), this);
        getLogger().info(TextFormat.GREEN + "KingOfTheHill загружен!");
    }

    @Override
    public void onDisable() {
        stopEvent();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("koth")) return false;
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
            case "leave":
                return handleLeave(sender);
            case "score":
                return handleScore(sender);
            case "top":
                return handleTop(sender);
            case "setzone":
                return handleSetZone(sender, args);
            case "reload":
                return handleReload(sender);
            default:
                sendHelp(sender);
                return true;
        }
    }

    private boolean handleStart(CommandSender sender, String[] args) {
        if (!sender.hasPermission("koth.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (eventActive) {
            sender.sendMessage(TextFormat.RED + "Ивент уже идёт!");
            return true;
        }
        loadZone();
        if (zoneWorld == null) {
            sender.sendMessage(TextFormat.RED + "Зона не настроена! Используйте /koth setzone");
            return true;
        }
        startEvent();
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("koth.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        stopEvent();
        sender.sendMessage(TextFormat.GREEN + "KOTH остановлен!");
        return true;
    }

    private boolean handleJoin(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!eventActive) {
            player.sendMessage(msg("event-not-active"));
            return true;
        }
        participants.add(player.getName());
        scores.putIfAbsent(player.getName(), 0);
        player.sendMessage(msg("joined"));
        return true;
    }

    private boolean handleLeave(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        participants.remove(player.getName());
        if (player.getName().equals(currentKing)) {
            currentKing = null;
        }
        player.sendMessage(msg("left"));
        return true;
    }

    private boolean handleScore(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        int score = scores.getOrDefault(player.getName(), 0);
        player.sendMessage(TextFormat.GOLD + "Ваш счёт: " + TextFormat.WHITE + score + "/" + pointsToWin);
        if (currentKing != null) {
            player.sendMessage(TextFormat.YELLOW + "Текущий король: " + TextFormat.WHITE + currentKing
                    + " (" + scores.getOrDefault(currentKing, 0) + " очков)");
        }
        return true;
    }

    private boolean handleTop(CommandSender sender) {
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(scores.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        sender.sendMessage(TextFormat.GOLD + "=== Топ KOTH ===");
        int rank = 1;
        for (Map.Entry<String, Integer> entry : sorted) {
            if (rank > 10) break;
            String prefix = entry.getKey().equals(currentKing) ? TextFormat.RED + "[KING] " : "";
            sender.sendMessage(TextFormat.YELLOW + "#" + rank + " " + prefix + entry.getKey()
                    + TextFormat.GRAY + " — " + TextFormat.WHITE + entry.getValue() + "/" + pointsToWin);
            rank++;
        }
        return true;
    }

    private boolean handleSetZone(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("koth.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/koth setzone <pos1|pos2>");
            return true;
        }
        Config config = getConfig();
        if (args[1].equalsIgnoreCase("pos1")) {
            config.set("zone.pos1.world", player.getLevel().getName());
            config.set("zone.pos1.x", player.getX());
            config.set("zone.pos1.y", player.getY());
            config.set("zone.pos1.z", player.getZ());
            config.save();
            player.sendMessage(TextFormat.GREEN + "Позиция 1 установлена!");
        } else if (args[1].equalsIgnoreCase("pos2")) {
            config.set("zone.pos2.world", player.getLevel().getName());
            config.set("zone.pos2.x", player.getX());
            config.set("zone.pos2.y", player.getY());
            config.set("zone.pos2.z", player.getZ());
            config.save();
            player.sendMessage(TextFormat.GREEN + "Позиция 2 установлена!");
        }
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("koth.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        sender.sendMessage(TextFormat.GREEN + "KOTH перезагружен!");
        return true;
    }

    private void loadZone() {
        Config config = getConfig();
        if (!config.exists("zone.pos1") || !config.exists("zone.pos2")) {
            zoneWorld = null;
            return;
        }
        zoneWorld = config.getString("zone.pos1.world");
        zoneX1 = Math.min(config.getDouble("zone.pos1.x"), config.getDouble("zone.pos2.x"));
        zoneY1 = Math.min(config.getDouble("zone.pos1.y"), config.getDouble("zone.pos2.y"));
        zoneZ1 = Math.min(config.getDouble("zone.pos1.z"), config.getDouble("zone.pos2.z"));
        zoneX2 = Math.max(config.getDouble("zone.pos1.x"), config.getDouble("zone.pos2.x"));
        zoneY2 = Math.max(config.getDouble("zone.pos1.y"), config.getDouble("zone.pos2.y"));
        zoneZ2 = Math.max(config.getDouble("zone.pos1.z"), config.getDouble("zone.pos2.z"));
        pointsToWin = config.getInt("settings.points-to-win", 300);
    }

    private void startEvent() {
        eventActive = true;
        scores.clear();
        participants.clear();
        currentKing = null;
        eventTimer = getConfig().getInt("settings.event-duration", 900);
        pointsToWin = getConfig().getInt("settings.points-to-win", 300);

        getServer().broadcastMessage(msg("event-started")
                .replace("{time}", formatTime(eventTimer))
                .replace("{points}", String.valueOf(pointsToWin)));

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(TextFormat.RED + "ЦАРЬ ГОРЫ!",
                    TextFormat.YELLOW + "/koth join", 10, 60, 10);
        }

        int scoreInterval = getConfig().getInt("settings.score-interval", 1);

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            private int scoreTick = 0;

            @Override
            public void onRun(int currentTick) {
                if (!eventActive || eventTimer <= 0) {
                    endEvent();
                    this.getHandler().cancel();
                    return;
                }

                scoreTick++;
                if (scoreTick >= scoreInterval) {
                    scoreTick = 0;
                    tickScoring();
                }

                if (eventTimer == 60 || eventTimer == 30 || eventTimer == 10) {
                    broadcastToParticipants(msg("time-remaining")
                            .replace("{time}", formatTime(eventTimer)));
                }
                eventTimer--;
            }
        }, 20).getTaskId();
    }

    private void tickScoring() {
        String previousKing = currentKing;
        currentKing = null;

        for (String playerName : participants) {
            Player player = getServer().getPlayerExact(playerName);
            if (player == null) continue;
            if (!player.getLevel().getName().equals(zoneWorld)) continue;

            double px = player.getX();
            double py = player.getY();
            double pz = player.getZ();

            if (px >= zoneX1 && px <= zoneX2 && py >= zoneY1 && py <= zoneY2 && pz >= zoneZ1 && pz <= zoneZ2) {
                if (currentKing == null) {
                    currentKing = playerName;
                } else {
                    currentKing = null;
                    break;
                }
            }
        }

        if (currentKing != null) {
            scores.merge(currentKing, 1, Integer::sum);
            int score = scores.get(currentKing);

            if (!currentKing.equals(previousKing)) {
                broadcastToParticipants(msg("new-king").replace("{player}", currentKing));
            }

            if (score >= pointsToWin) {
                endEventWithWinner(currentKing);
            }
        }
    }

    private void endEventWithWinner(String winner) {
        eventActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        getServer().broadcastMessage(msg("winner")
                .replace("{player}", winner)
                .replace("{score}", String.valueOf(scores.getOrDefault(winner, 0))));

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(TextFormat.GOLD + "ЦАРЬ ГОРЫ!",
                    TextFormat.YELLOW + winner + " побеждает!",
                    10, 60, 10);
        }

        broadcastResults();
    }

    private void endEvent() {
        eventActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        if (!scores.isEmpty()) {
            String topPlayer = scores.entrySet().stream()
                    .max(Map.Entry.comparingByValue())
                    .map(Map.Entry::getKey).orElse("Никто");

            getServer().broadcastMessage(msg("event-ended")
                    .replace("{player}", topPlayer));
        }

        broadcastResults();
    }

    private void broadcastResults() {
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(scores.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        getServer().broadcastMessage(TextFormat.GOLD + "=== Результаты KOTH ===");
        int rank = 1;
        for (Map.Entry<String, Integer> entry : sorted) {
            if (rank > 5) break;
            String medal = rank == 1 ? "§6★" : rank == 2 ? "§7★" : rank == 3 ? "§c★" : "§7 ";
            getServer().broadcastMessage(medal + " #" + rank + " " + entry.getKey()
                    + " §7— §e" + entry.getValue() + " очков");
            rank++;
        }
    }

    public void stopEvent() {
        eventActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
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

    private String formatTime(int seconds) {
        return String.format("%d:%02d", seconds / 60, seconds % 60);
    }

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        return TextFormat.colorize(msgConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public boolean isEventActive() {
        return eventActive;
    }

    public Set<String> getParticipants() {
        return participants;
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== KingOfTheHill ===");
        sender.sendMessage(TextFormat.YELLOW + "/koth join" + TextFormat.GRAY + " — Присоединиться");
        sender.sendMessage(TextFormat.YELLOW + "/koth leave" + TextFormat.GRAY + " — Покинуть");
        sender.sendMessage(TextFormat.YELLOW + "/koth score" + TextFormat.GRAY + " — Ваш счёт");
        sender.sendMessage(TextFormat.YELLOW + "/koth top" + TextFormat.GRAY + " — Таблица лидеров");
        if (sender.hasPermission("koth.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/koth start" + TextFormat.GRAY + " — Начать ивент");
            sender.sendMessage(TextFormat.YELLOW + "/koth stop" + TextFormat.GRAY + " — Остановить");
            sender.sendMessage(TextFormat.YELLOW + "/koth setzone <pos1|pos2>" + TextFormat.GRAY + " — Задать зону захвата");
            sender.sendMessage(TextFormat.YELLOW + "/koth reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
