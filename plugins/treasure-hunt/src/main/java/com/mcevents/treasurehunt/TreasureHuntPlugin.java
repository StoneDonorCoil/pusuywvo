package com.mcevents.treasurehunt;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.level.Position;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class TreasureHuntPlugin extends PluginBase {

    private final Map<String, TreasurePoint> treasures = new LinkedHashMap<>();
    private final Map<String, Set<String>> playerFoundTreasures = new HashMap<>();
    private final Map<String, Integer> playerScores = new HashMap<>();
    private boolean eventActive = false;
    private int eventTimer;
    private int taskId = -1;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        getServer().getPluginManager().registerEvents(new TreasureListener(this), this);
        getLogger().info(TextFormat.GREEN + "TreasureHunt загружен!");
    }

    @Override
    public void onDisable() {
        stopEvent();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("th")) return false;

        if (args.length == 0) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "start":
                return handleStart(sender);
            case "stop":
                return handleStop(sender);
            case "addtreasure":
                return handleAddTreasure(sender, args);
            case "removetreasure":
                return handleRemoveTreasure(sender, args);
            case "hint":
                return handleHint(sender);
            case "score":
                return handleScore(sender);
            case "top":
                return handleTop(sender);
            case "list":
                return handleList(sender);
            case "reload":
                return handleReload(sender);
            default:
                sendHelp(sender);
                return true;
        }
    }

    private boolean handleStart(CommandSender sender) {
        if (!sender.hasPermission("th.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (eventActive) {
            sender.sendMessage(TextFormat.RED + "Ивент уже запущен!");
            return true;
        }
        if (treasures.isEmpty()) {
            loadTreasuresFromConfig();
        }
        if (treasures.isEmpty()) {
            sender.sendMessage(TextFormat.RED + "Нет сокровищ! Добавьте через /th addtreasure");
            return true;
        }
        startEvent();
        sender.sendMessage(TextFormat.GREEN + "Ивент Охота за Сокровищами запущен!");
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("th.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (!eventActive) {
            sender.sendMessage(TextFormat.RED + "Ивент не запущен!");
            return true;
        }
        stopEvent();
        sender.sendMessage(TextFormat.GREEN + "Ивент остановлен!");
        return true;
    }

    private boolean handleAddTreasure(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("th.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/th addtreasure <название> [уровень: 1-5]");
            return true;
        }
        String treasureName = args[1].toLowerCase();
        int tier = args.length >= 3 ? parseTier(args[2]) : 1;

        Position pos = player.getPosition();
        TreasurePoint tp = new TreasurePoint(treasureName, pos.getX(), pos.getY(), pos.getZ(),
                pos.getLevel().getName(), tier);
        treasures.put(treasureName, tp);
        saveTreasureToConfig(treasureName, tp);

        player.sendMessage(TextFormat.GREEN + "Сокровище '" + treasureName + "' (уровень " + tier + ") добавлено на вашей позиции!");
        return true;
    }

    private boolean handleRemoveTreasure(CommandSender sender, String[] args) {
        if (!sender.hasPermission("th.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            sender.sendMessage(TextFormat.RED + "/th removetreasure <название>");
            return true;
        }
        String name = args[1].toLowerCase();
        if (treasures.remove(name) != null) {
            getConfig().remove("treasures." + name);
            getConfig().save();
            sender.sendMessage(TextFormat.GREEN + "Сокровище '" + name + "' удалено!");
        } else {
            sender.sendMessage(TextFormat.RED + "Сокровище не найдено!");
        }
        return true;
    }

    private boolean handleHint(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!eventActive) {
            player.sendMessage(msg("event-not-active"));
            return true;
        }

        Set<String> found = playerFoundTreasures.getOrDefault(player.getName(), new HashSet<>());
        TreasurePoint nearest = null;
        double nearestDist = Double.MAX_VALUE;

        for (Map.Entry<String, TreasurePoint> entry : treasures.entrySet()) {
            if (found.contains(entry.getKey())) continue;
            if (!entry.getValue().getWorldName().equals(player.getLevel().getName())) continue;

            double dist = player.getPosition().distance(entry.getValue().toVector3());
            if (dist < nearestDist) {
                nearestDist = dist;
                nearest = entry.getValue();
            }
        }

        if (nearest == null) {
            player.sendMessage(msg("all-found"));
            return true;
        }

        String hint = getDistanceHint(nearestDist);
        String direction = getDirectionHint(player, nearest);
        player.sendMessage(msg("hint-message")
                .replace("{hint}", hint)
                .replace("{direction}", direction)
                .replace("{distance}", String.format("%.0f", nearestDist)));
        return true;
    }

    private boolean handleScore(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        int score = playerScores.getOrDefault(player.getName(), 0);
        Set<String> found = playerFoundTreasures.getOrDefault(player.getName(), new HashSet<>());
        player.sendMessage(TextFormat.GOLD + "=== Ваш счёт ===");
        player.sendMessage(TextFormat.YELLOW + "Очки: " + TextFormat.WHITE + score);
        player.sendMessage(TextFormat.YELLOW + "Найдено: " + TextFormat.WHITE + found.size() + "/" + treasures.size());
        return true;
    }

    private boolean handleTop(CommandSender sender) {
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(playerScores.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        sender.sendMessage(TextFormat.GOLD + "=== Топ охотников ===");
        int rank = 1;
        for (Map.Entry<String, Integer> entry : sorted) {
            if (rank > 10) break;
            sender.sendMessage(TextFormat.YELLOW + "#" + rank + " " + entry.getKey()
                    + TextFormat.GRAY + " — " + TextFormat.WHITE + entry.getValue() + " очков");
            rank++;
        }
        if (sorted.isEmpty()) {
            sender.sendMessage(TextFormat.GRAY + "Пока никто не нашёл сокровищ.");
        }
        return true;
    }

    private boolean handleList(CommandSender sender) {
        if (!sender.hasPermission("th.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (treasures.isEmpty()) {
            sender.sendMessage(TextFormat.YELLOW + "Нет сокровищ.");
            return true;
        }
        sender.sendMessage(TextFormat.GOLD + "=== Сокровища ===");
        for (Map.Entry<String, TreasurePoint> entry : treasures.entrySet()) {
            TreasurePoint tp = entry.getValue();
            sender.sendMessage(TextFormat.YELLOW + "  " + entry.getKey()
                    + TextFormat.GRAY + " [ур." + tp.getTier() + "] "
                    + TextFormat.WHITE + String.format("(%.0f, %.0f, %.0f) %s",
                    tp.getX(), tp.getY(), tp.getZ(), tp.getWorldName()));
        }
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("th.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        loadTreasuresFromConfig();
        sender.sendMessage(TextFormat.GREEN + "TreasureHunt перезагружен!");
        return true;
    }

    private void startEvent() {
        eventActive = true;
        playerFoundTreasures.clear();
        playerScores.clear();
        eventTimer = getConfig().getInt("settings.event-duration", 1800);

        String announcement = msg("event-started")
                .replace("{treasures}", String.valueOf(treasures.size()))
                .replace("{time}", formatTime(eventTimer));
        getServer().broadcastMessage(announcement);

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(
                    TextFormat.GOLD + "ОХОТА ЗА СОКРОВИЩАМИ!",
                    TextFormat.YELLOW + "Найди все сокровища!",
                    10, 60, 10);
        }

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (eventTimer <= 0) {
                    endEvent();
                    this.getHandler().cancel();
                    return;
                }
                if (eventTimer == 300 || eventTimer == 60 || eventTimer == 30 || eventTimer == 10) {
                    getServer().broadcastMessage(msg("time-remaining")
                            .replace("{time}", formatTime(eventTimer)));
                }
                eventTimer--;
            }
        }, 20).getTaskId();
    }

    private void endEvent() {
        eventActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        getServer().broadcastMessage(msg("event-ended"));

        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(playerScores.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        if (!sorted.isEmpty()) {
            getServer().broadcastMessage(TextFormat.GOLD + "=== Результаты Охоты за Сокровищами ===");
            int rank = 1;
            for (Map.Entry<String, Integer> entry : sorted) {
                if (rank > 3) break;
                String medal = rank == 1 ? "§6★" : rank == 2 ? "§7★" : "§c★";
                getServer().broadcastMessage(medal + " #" + rank + " " + entry.getKey()
                        + " §7— §e" + entry.getValue() + " очков");
                rank++;
            }
        }
    }

    public void stopEvent() {
        if (eventActive) {
            endEvent();
        }
    }

    public void onPlayerFoundTreasure(Player player, TreasurePoint treasure) {
        String playerName = player.getName();
        playerFoundTreasures.computeIfAbsent(playerName, k -> new HashSet<>());

        String treasureKey = null;
        for (Map.Entry<String, TreasurePoint> entry : treasures.entrySet()) {
            if (entry.getValue().equals(treasure)) {
                treasureKey = entry.getKey();
                break;
            }
        }
        if (treasureKey == null) return;

        if (playerFoundTreasures.get(playerName).contains(treasureKey)) return;

        playerFoundTreasures.get(playerName).add(treasureKey);
        int points = getPointsForTier(treasure.getTier());
        playerScores.merge(playerName, points, Integer::sum);

        player.sendMessage(msg("treasure-found")
                .replace("{treasure}", treasureKey)
                .replace("{tier}", String.valueOf(treasure.getTier()))
                .replace("{points}", String.valueOf(points)));

        player.sendTitle(TextFormat.GOLD + "+" + points, TextFormat.YELLOW + "Сокровище найдено!", 5, 30, 5);

        int totalFound = playerFoundTreasures.get(playerName).size();
        if (totalFound == treasures.size()) {
            getServer().broadcastMessage(msg("all-treasures-found")
                    .replace("{player}", playerName));
        }
    }

    private void loadTreasuresFromConfig() {
        treasures.clear();
        Config config = getConfig();
        if (!config.exists("treasures")) return;

        for (String name : config.getSection("treasures").getKeys(false)) {
            cn.nukkit.utils.ConfigSection section = config.getSection("treasures." + name);
            TreasurePoint tp = new TreasurePoint(
                    name,
                    section.getDouble("x"),
                    section.getDouble("y"),
                    section.getDouble("z"),
                    section.getString("world", "world"),
                    section.getInt("tier", 1)
            );
            treasures.put(name, tp);
        }
    }

    private void saveTreasureToConfig(String name, TreasurePoint tp) {
        Config config = getConfig();
        String path = "treasures." + name;
        config.set(path + ".x", tp.getX());
        config.set(path + ".y", tp.getY());
        config.set(path + ".z", tp.getZ());
        config.set(path + ".world", tp.getWorldName());
        config.set(path + ".tier", tp.getTier());
        config.save();
    }

    private int getPointsForTier(int tier) {
        return getConfig().getInt("settings.tier-points." + tier,
                switch (tier) {
                    case 1 -> 10;
                    case 2 -> 25;
                    case 3 -> 50;
                    case 4 -> 100;
                    case 5 -> 250;
                    default -> 10;
                });
    }

    private String getDistanceHint(double distance) {
        if (distance > 200) return TextFormat.BLUE + "Ледяной холод...";
        if (distance > 100) return TextFormat.AQUA + "Холодно";
        if (distance > 50) return TextFormat.GREEN + "Тепло";
        if (distance > 20) return TextFormat.YELLOW + "Горячо!";
        if (distance > 10) return TextFormat.RED + "ОЧЕНЬ ГОРЯЧО!";
        return TextFormat.DARK_RED + "ОГОНЬ!! Совсем рядом!";
    }

    private String getDirectionHint(Player player, TreasurePoint tp) {
        double dx = tp.getX() - player.getX();
        double dz = tp.getZ() - player.getZ();
        double angle = Math.toDegrees(Math.atan2(-dx, dz));
        double playerYaw = player.getYaw();
        double relative = ((angle - playerYaw) % 360 + 360) % 360;

        if (relative < 22.5 || relative >= 337.5) return "Впереди";
        if (relative < 67.5) return "Впереди-справа";
        if (relative < 112.5) return "Справа";
        if (relative < 157.5) return "Сзади-справа";
        if (relative < 202.5) return "Сзади";
        if (relative < 247.5) return "Сзади-слева";
        if (relative < 292.5) return "Слева";
        return "Впереди-слева";
    }

    private int parseTier(String s) {
        try {
            int t = Integer.parseInt(s);
            return Math.max(1, Math.min(5, t));
        } catch (NumberFormatException e) {
            return 1;
        }
    }

    private String formatTime(int seconds) {
        int min = seconds / 60;
        int sec = seconds % 60;
        return String.format("%d:%02d", min, sec);
    }

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        String message = msgConfig.getString(key, "&cСообщение не найдено: " + key);
        return TextFormat.colorize(message);
    }

    public boolean isEventActive() {
        return eventActive;
    }

    public Map<String, TreasurePoint> getTreasures() {
        return treasures;
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== TreasureHunt ===");
        sender.sendMessage(TextFormat.YELLOW + "/th hint" + TextFormat.GRAY + " — Получить подсказку");
        sender.sendMessage(TextFormat.YELLOW + "/th score" + TextFormat.GRAY + " — Ваш счёт");
        sender.sendMessage(TextFormat.YELLOW + "/th top" + TextFormat.GRAY + " — Таблица лидеров");
        if (sender.hasPermission("th.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/th start" + TextFormat.GRAY + " — Запустить ивент");
            sender.sendMessage(TextFormat.YELLOW + "/th stop" + TextFormat.GRAY + " — Остановить ивент");
            sender.sendMessage(TextFormat.YELLOW + "/th addtreasure <имя> [уровень]" + TextFormat.GRAY + " — Добавить сокровище");
            sender.sendMessage(TextFormat.YELLOW + "/th removetreasure <имя>" + TextFormat.GRAY + " — Удалить сокровище");
            sender.sendMessage(TextFormat.YELLOW + "/th list" + TextFormat.GRAY + " — Список сокровищ");
            sender.sendMessage(TextFormat.YELLOW + "/th reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
