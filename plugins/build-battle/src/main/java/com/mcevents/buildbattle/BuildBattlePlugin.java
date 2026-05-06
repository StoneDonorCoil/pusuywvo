package com.mcevents.buildbattle;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.level.Position;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class BuildBattlePlugin extends PluginBase {

    public enum GameState {
        WAITING, BUILDING, VOTING, ENDED
    }

    private GameState state = GameState.WAITING;
    private final Map<String, BuildPlot> plots = new LinkedHashMap<>();
    private final List<String> participants = new ArrayList<>();
    private final Map<String, Map<String, Integer>> votes = new HashMap<>();
    private String currentTheme;
    private int timer;
    private int taskId = -1;
    private int currentVotingIndex = -1;
    private Config messagesConfig;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        messagesConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        getServer().getPluginManager().registerEvents(new BuildListener(this), this);
        getLogger().info(TextFormat.GREEN + "BuildBattle загружен!");
    }

    @Override
    public void onDisable() {
        forceStop();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("bb")) return false;
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
                return handleStart(sender, args);
            case "stop":
                return handleStop(sender);
            case "vote":
                return handleVote(sender, args);
            case "addplot":
                return handleAddPlot(sender, args);
            case "theme":
                return handleTheme(sender);
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
        if (state != GameState.WAITING) {
            player.sendMessage(msg("game-in-progress"));
            return true;
        }
        if (participants.contains(player.getName())) {
            player.sendMessage(TextFormat.YELLOW + "Вы уже зарегистрированы!");
            return true;
        }
        int maxPlayers = getConfig().getInt("settings.max-players", 12);
        if (participants.size() >= maxPlayers) {
            player.sendMessage(msg("game-full"));
            return true;
        }
        participants.add(player.getName());
        player.sendMessage(msg("joined")
                .replace("{count}", String.valueOf(participants.size()))
                .replace("{max}", String.valueOf(maxPlayers)));
        return true;
    }

    private boolean handleLeave(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!participants.contains(player.getName())) {
            player.sendMessage(TextFormat.RED + "Вы не участвуете!");
            return true;
        }
        participants.remove(player.getName());
        plots.remove(player.getName());
        player.sendMessage(msg("left"));
        return true;
    }

    private boolean handleStart(CommandSender sender, String[] args) {
        if (!sender.hasPermission("bb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (state != GameState.WAITING) {
            sender.sendMessage(TextFormat.RED + "Игра уже идёт!");
            return true;
        }
        if (participants.size() < getConfig().getInt("settings.min-players", 2)) {
            sender.sendMessage(TextFormat.RED + "Недостаточно игроков!");
            return true;
        }
        if (args.length >= 2) {
            currentTheme = String.join(" ", Arrays.copyOfRange(args, 1, args.length));
        } else {
            currentTheme = selectRandomTheme();
        }
        startBuildPhase();
        sender.sendMessage(TextFormat.GREEN + "Битва Строителей начата! Тема: " + currentTheme);
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("bb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        forceStop();
        sender.sendMessage(TextFormat.GREEN + "Игра остановлена!");
        return true;
    }

    private boolean handleVote(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (state != GameState.VOTING) {
            player.sendMessage(TextFormat.RED + "Голосование не активно!");
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/bb vote <1-5>");
            return true;
        }
        int score;
        try {
            score = Integer.parseInt(args[1]);
            if (score < 1 || score > 5) throw new NumberFormatException();
        } catch (NumberFormatException e) {
            player.sendMessage(TextFormat.RED + "Оценка должна быть от 1 до 5!");
            return true;
        }

        if (currentVotingIndex < 0 || currentVotingIndex >= participants.size()) return true;
        String builder = participants.get(currentVotingIndex);

        if (builder.equals(player.getName())) {
            player.sendMessage(TextFormat.RED + "Нельзя голосовать за себя!");
            return true;
        }

        votes.computeIfAbsent(builder, k -> new HashMap<>()).put(player.getName(), score);
        player.sendMessage(TextFormat.GREEN + "Вы поставили оценку " + score + " за постройку " + builder + "!");
        return true;
    }

    private boolean handleAddPlot(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("bb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/bb addplot <номер>");
            return true;
        }
        String plotId = args[1];
        Config config = getConfig();
        String path = "plots." + plotId;
        config.set(path + ".world", player.getLevel().getName());
        config.set(path + ".x", player.getX());
        config.set(path + ".y", player.getY());
        config.set(path + ".z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Участок #" + plotId + " добавлен!");
        return true;
    }

    private boolean handleTheme(CommandSender sender) {
        if (currentTheme == null) {
            sender.sendMessage(TextFormat.YELLOW + "Тема ещё не выбрана.");
        } else {
            sender.sendMessage(TextFormat.GOLD + "Тема: " + TextFormat.WHITE + currentTheme);
        }
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("bb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        messagesConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        sender.sendMessage(TextFormat.GREEN + "BuildBattle перезагружен!");
        return true;
    }

    private void startBuildPhase() {
        state = GameState.BUILDING;
        timer = getConfig().getInt("settings.build-time", 300);

        assignPlots();

        for (String playerName : participants) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.sendTitle(TextFormat.GOLD + "ТЕМА:", TextFormat.YELLOW + currentTheme, 10, 60, 10);
                player.sendMessage(msg("build-started")
                        .replace("{theme}", currentTheme)
                        .replace("{time}", formatTime(timer)));
                player.setGamemode(Player.CREATIVE);
            }
        }

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (timer <= 0) {
                    startVotingPhase();
                    this.getHandler().cancel();
                    return;
                }
                if (timer == 60 || timer == 30 || timer == 10 || timer <= 5) {
                    broadcastToPlayers(msg("time-left").replace("{time}", String.valueOf(timer)));
                }
                timer--;
            }
        }, 20).getTaskId();
    }

    private void startVotingPhase() {
        state = GameState.VOTING;
        currentVotingIndex = 0;
        votes.clear();

        broadcastToPlayers(msg("voting-started"));
        for (String playerName : participants) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.setGamemode(Player.ADVENTURE);
            }
        }

        showNextPlot();
    }

    private void showNextPlot() {
        if (currentVotingIndex >= participants.size()) {
            endGame();
            return;
        }

        String builder = participants.get(currentVotingIndex);
        BuildPlot plot = plots.get(builder);

        broadcastToPlayers(msg("now-voting")
                .replace("{player}", builder)
                .replace("{number}", String.valueOf(currentVotingIndex + 1))
                .replace("{total}", String.valueOf(participants.size())));

        if (plot != null && plot.getPosition() != null) {
            for (String playerName : participants) {
                Player player = getServer().getPlayerExact(playerName);
                if (player != null) {
                    player.teleport(plot.getPosition());
                }
            }
        }

        int votingTime = getConfig().getInt("settings.voting-time-per-plot", 20);
        timer = votingTime;

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (timer <= 0) {
                    currentVotingIndex++;
                    showNextPlot();
                    this.getHandler().cancel();
                    return;
                }
                if (timer <= 5) {
                    broadcastToPlayers(TextFormat.YELLOW + "Осталось " + timer + " сек для голосования! /bb vote <1-5>");
                }
                timer--;
            }
        }, 20).getTaskId();
    }

    private void endGame() {
        state = GameState.ENDED;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }

        Map<String, Double> averages = new LinkedHashMap<>();
        for (String builder : participants) {
            Map<String, Integer> builderVotes = votes.getOrDefault(builder, new HashMap<>());
            if (builderVotes.isEmpty()) {
                averages.put(builder, 0.0);
            } else {
                double avg = builderVotes.values().stream().mapToInt(Integer::intValue).average().orElse(0);
                averages.put(builder, avg);
            }
        }

        List<Map.Entry<String, Double>> sorted = new ArrayList<>(averages.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        broadcastToPlayers(TextFormat.GOLD + "=== Результаты Битвы Строителей ===");
        broadcastToPlayers(TextFormat.YELLOW + "Тема: " + TextFormat.WHITE + currentTheme);

        int rank = 1;
        for (Map.Entry<String, Double> entry : sorted) {
            String medal = rank == 1 ? "§6★" : rank == 2 ? "§7★" : rank == 3 ? "§c★" : "§7 ";
            broadcastToPlayers(medal + " #" + rank + " " + entry.getKey()
                    + " §7— §e" + String.format("%.1f / 5.0", entry.getValue()));
            rank++;
        }

        if (!sorted.isEmpty()) {
            String winner = sorted.get(0).getKey();
            for (Player player : getServer().getOnlinePlayers().values()) {
                player.sendTitle(TextFormat.GOLD + "ПОБЕДИТЕЛЬ!",
                        TextFormat.YELLOW + winner + " (" + String.format("%.1f", sorted.get(0).getValue()) + "/5.0)",
                        10, 60, 10);
            }
        }

        getServer().getScheduler().scheduleDelayedTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                resetGame();
            }
        }, 100);
    }

    private void assignPlots() {
        Config config = getConfig();
        List<String> plotKeys = config.exists("plots")
                ? new ArrayList<>(config.getSection("plots").getKeys(false))
                : new ArrayList<>();

        for (int i = 0; i < participants.size(); i++) {
            String playerName = participants.get(i);
            Position pos = null;

            if (i < plotKeys.size()) {
                cn.nukkit.utils.ConfigSection plotSection = config.getSection("plots." + plotKeys.get(i));
                String worldName = plotSection.getString("world", "world");
                cn.nukkit.level.Level level = getServer().getLevelByName(worldName);
                if (level != null) {
                    pos = new Position(plotSection.getDouble("x"), plotSection.getDouble("y"),
                            plotSection.getDouble("z"), level);
                }
            }

            BuildPlot plot = new BuildPlot(playerName, pos);
            plots.put(playerName, plot);

            Player player = getServer().getPlayerExact(playerName);
            if (player != null && pos != null) {
                player.teleport(pos);
            }
        }
    }

    private String selectRandomTheme() {
        List<String> themes = getConfig().getStringList("settings.themes");
        if (themes.isEmpty()) {
            themes = Arrays.asList("Замок", "Космос", "Подводный мир", "Средневековье",
                    "Будущее", "Природа", "Пиратский корабль", "Японский сад");
        }
        return themes.get(new Random().nextInt(themes.size()));
    }

    public void forceStop() {
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        resetGame();
    }

    private void resetGame() {
        for (String playerName : participants) {
            Player player = getServer().getPlayerExact(playerName);
            if (player != null) {
                player.setGamemode(Player.SURVIVAL);
                player.teleport(getServer().getDefaultLevel().getSpawnLocation());
            }
        }
        participants.clear();
        plots.clear();
        votes.clear();
        currentTheme = null;
        currentVotingIndex = -1;
        state = GameState.WAITING;
    }

    private void broadcastToPlayers(String message) {
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
        return TextFormat.colorize(messagesConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public GameState getState() {
        return state;
    }

    public List<String> getParticipants() {
        return participants;
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== BuildBattle ===");
        sender.sendMessage(TextFormat.YELLOW + "/bb join" + TextFormat.GRAY + " — Присоединиться");
        sender.sendMessage(TextFormat.YELLOW + "/bb leave" + TextFormat.GRAY + " — Покинуть");
        sender.sendMessage(TextFormat.YELLOW + "/bb theme" + TextFormat.GRAY + " — Текущая тема");
        sender.sendMessage(TextFormat.YELLOW + "/bb vote <1-5>" + TextFormat.GRAY + " — Голосовать");
        if (sender.hasPermission("bb.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/bb start [тема]" + TextFormat.GRAY + " — Начать игру");
            sender.sendMessage(TextFormat.YELLOW + "/bb stop" + TextFormat.GRAY + " — Остановить");
            sender.sendMessage(TextFormat.YELLOW + "/bb addplot <номер>" + TextFormat.GRAY + " — Добавить участок");
            sender.sendMessage(TextFormat.YELLOW + "/bb reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
