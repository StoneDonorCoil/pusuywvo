package com.mcevents.survivalgames;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.TextFormat;

import java.util.HashMap;
import java.util.Map;

public class SurvivalGamesPlugin extends PluginBase {

    private final Map<String, GameArena> arenas = new HashMap<>();
    private final Map<String, String> playerArenaMap = new HashMap<>();
    private Config messagesConfig;

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        messagesConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        loadArenas();
        getServer().getPluginManager().registerEvents(new GameListener(this), this);
        getLogger().info(TextFormat.GREEN + "SurvivalGames загружен! Арен: " + arenas.size());
    }

    @Override
    public void onDisable() {
        for (GameArena arena : arenas.values()) {
            arena.forceStop();
        }
        getLogger().info(TextFormat.RED + "SurvivalGames выключен!");
    }

    private void loadArenas() {
        arenas.clear();
        Config config = getConfig();
        if (config.exists("arenas")) {
            for (String arenaName : config.getSection("arenas").getKeys(false)) {
                GameArena arena = new GameArena(this, arenaName, config.getSection("arenas." + arenaName));
                arenas.put(arenaName.toLowerCase(), arena);
            }
        }
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("sg")) {
            return false;
        }

        if (args.length == 0) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "join":
                return handleJoin(sender, args);
            case "leave":
                return handleLeave(sender);
            case "start":
                return handleStart(sender, args);
            case "stop":
                return handleStop(sender, args);
            case "setspawn":
                return handleSetSpawn(sender, args);
            case "setlobby":
                return handleSetLobby(sender, args);
            case "create":
                return handleCreate(sender, args);
            case "list":
                return handleList(sender);
            case "reload":
                return handleReload(sender);
            default:
                sendHelp(sender);
                return true;
        }
    }

    private boolean handleJoin(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(msg("usage-join"));
            return true;
        }
        String arenaName = args[1].toLowerCase();
        GameArena arena = arenas.get(arenaName);
        if (arena == null) {
            player.sendMessage(msg("arena-not-found").replace("{arena}", arenaName));
            return true;
        }
        if (playerArenaMap.containsKey(player.getName())) {
            player.sendMessage(msg("already-in-game"));
            return true;
        }
        if (!arena.addPlayer(player)) {
            player.sendMessage(msg("arena-full"));
            return true;
        }
        playerArenaMap.put(player.getName(), arenaName);
        return true;
    }

    private boolean handleLeave(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        String arenaName = playerArenaMap.get(player.getName());
        if (arenaName == null) {
            player.sendMessage(msg("not-in-game"));
            return true;
        }
        GameArena arena = arenas.get(arenaName);
        if (arena != null) {
            arena.removePlayer(player);
        }
        playerArenaMap.remove(player.getName());
        return true;
    }

    private boolean handleStart(CommandSender sender, String[] args) {
        if (!sender.hasPermission("sg.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            sender.sendMessage(TextFormat.RED + "/sg start <арена>");
            return true;
        }
        GameArena arena = arenas.get(args[1].toLowerCase());
        if (arena == null) {
            sender.sendMessage(msg("arena-not-found").replace("{arena}", args[1]));
            return true;
        }
        arena.forceStart();
        sender.sendMessage(TextFormat.GREEN + "Арена " + args[1] + " запущена принудительно!");
        return true;
    }

    private boolean handleStop(CommandSender sender, String[] args) {
        if (!sender.hasPermission("sg.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            sender.sendMessage(TextFormat.RED + "/sg stop <арена>");
            return true;
        }
        GameArena arena = arenas.get(args[1].toLowerCase());
        if (arena == null) {
            sender.sendMessage(msg("arena-not-found").replace("{arena}", args[1]));
            return true;
        }
        arena.forceStop();
        sender.sendMessage(TextFormat.GREEN + "Арена " + args[1] + " остановлена!");
        return true;
    }

    private boolean handleSetSpawn(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("sg.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 3) {
            player.sendMessage(TextFormat.RED + "/sg setspawn <арена> <номер>");
            return true;
        }
        String arenaName = args[1].toLowerCase();
        int index;
        try {
            index = Integer.parseInt(args[2]);
        } catch (NumberFormatException e) {
            player.sendMessage(TextFormat.RED + "Номер спавна должен быть числом!");
            return true;
        }
        Config config = getConfig();
        String path = "arenas." + arenaName + ".spawns." + index;
        config.set(path + ".world", player.getLevel().getName());
        config.set(path + ".x", player.getX());
        config.set(path + ".y", player.getY());
        config.set(path + ".z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Спавн #" + index + " установлен для арены " + arenaName + "!");
        return true;
    }

    private boolean handleSetLobby(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("sg.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/sg setlobby <арена>");
            return true;
        }
        String arenaName = args[1].toLowerCase();
        Config config = getConfig();
        String path = "arenas." + arenaName + ".lobby";
        config.set(path + ".world", player.getLevel().getName());
        config.set(path + ".x", player.getX());
        config.set(path + ".y", player.getY());
        config.set(path + ".z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + "Лобби установлено для арены " + arenaName + "!");
        return true;
    }

    private boolean handleCreate(CommandSender sender, String[] args) {
        if (!sender.hasPermission("sg.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            sender.sendMessage(TextFormat.RED + "/sg create <название>");
            return true;
        }
        String arenaName = args[1].toLowerCase();
        if (arenas.containsKey(arenaName)) {
            sender.sendMessage(TextFormat.RED + "Арена с таким названием уже существует!");
            return true;
        }
        Config config = getConfig();
        config.set("arenas." + arenaName + ".min-players", config.getInt("settings.min-players", 4));
        config.set("arenas." + arenaName + ".max-players", config.getInt("settings.max-players", 24));
        config.save();
        loadArenas();
        sender.sendMessage(TextFormat.GREEN + "Арена " + arenaName + " создана! Настройте спавны: /sg setspawn " + arenaName + " <номер>");
        return true;
    }

    private boolean handleList(CommandSender sender) {
        if (arenas.isEmpty()) {
            sender.sendMessage(TextFormat.YELLOW + "Нет доступных арен.");
            return true;
        }
        sender.sendMessage(TextFormat.GOLD + "=== Арены SurvivalGames ===");
        for (Map.Entry<String, GameArena> entry : arenas.entrySet()) {
            GameArena arena = entry.getValue();
            sender.sendMessage(TextFormat.YELLOW + "  " + entry.getKey()
                    + TextFormat.GRAY + " [" + arena.getState().name()
                    + "] " + TextFormat.WHITE + arena.getPlayerCount() + "/" + arena.getMaxPlayers());
        }
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("sg.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        messagesConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        loadArenas();
        sender.sendMessage(TextFormat.GREEN + "SurvivalGames перезагружен!");
        return true;
    }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== SurvivalGames ===");
        sender.sendMessage(TextFormat.YELLOW + "/sg join <арена>" + TextFormat.GRAY + " — Войти в арену");
        sender.sendMessage(TextFormat.YELLOW + "/sg leave" + TextFormat.GRAY + " — Покинуть арену");
        sender.sendMessage(TextFormat.YELLOW + "/sg list" + TextFormat.GRAY + " — Список арен");
        if (sender.hasPermission("sg.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/sg create <арена>" + TextFormat.GRAY + " — Создать арену");
            sender.sendMessage(TextFormat.YELLOW + "/sg setspawn <арена> <номер>" + TextFormat.GRAY + " — Установить спавн");
            sender.sendMessage(TextFormat.YELLOW + "/sg setlobby <арена>" + TextFormat.GRAY + " — Установить лобби");
            sender.sendMessage(TextFormat.YELLOW + "/sg start <арена>" + TextFormat.GRAY + " — Запустить принудительно");
            sender.sendMessage(TextFormat.YELLOW + "/sg stop <арена>" + TextFormat.GRAY + " — Остановить арену");
            sender.sendMessage(TextFormat.YELLOW + "/sg reload" + TextFormat.GRAY + " — Перезагрузить конфиг");
        }
    }

    public String msg(String key) {
        String message = messagesConfig.getString(key, "&cСообщение не найдено: " + key);
        return TextFormat.colorize(message);
    }

    public Map<String, GameArena> getArenas() {
        return arenas;
    }

    public Map<String, String> getPlayerArenaMap() {
        return playerArenaMap;
    }

    public void removePlayerFromMap(String playerName) {
        playerArenaMap.remove(playerName);
    }
}
