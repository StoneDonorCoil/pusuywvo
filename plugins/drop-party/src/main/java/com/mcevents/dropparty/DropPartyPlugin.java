package com.mcevents.dropparty;

import cn.nukkit.Player;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.entity.item.EntityItem;
import cn.nukkit.item.Item;
import cn.nukkit.level.Level;
import cn.nukkit.level.Position;
import cn.nukkit.math.Vector3;
import cn.nukkit.nbt.NBTIO;
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

public class DropPartyPlugin extends PluginBase {

    private boolean partyActive = false;
    private int partyTimer;
    private int taskId = -1;
    private int dropTaskId = -1;
    private final Map<String, Integer> playerPickups = new HashMap<>();
    private final Random random = new Random();

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        getServer().getPluginManager().registerEvents(new DropListener(this), this);
        getLogger().info(TextFormat.GREEN + "DropParty загружен!");
    }

    @Override
    public void onDisable() {
        stopParty();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("dp")) return false;
        if (args.length == 0) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "start":
                return handleStart(sender);
            case "stop":
                return handleStop(sender);
            case "setzone":
                return handleSetZone(sender, args);
            case "top":
                return handleTop(sender);
            case "reload":
                return handleReload(sender);
            default:
                sendHelp(sender);
                return true;
        }
    }

    private boolean handleStart(CommandSender sender) {
        if (!sender.hasPermission("dp.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (partyActive) {
            sender.sendMessage(TextFormat.RED + "Дроп-пати уже идёт!");
            return true;
        }
        if (!getConfig().exists("zone.pos1") || !getConfig().exists("zone.pos2")) {
            sender.sendMessage(TextFormat.RED + "Зона не настроена! /dp setzone pos1 и /dp setzone pos2");
            return true;
        }
        startParty();
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("dp.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        stopParty();
        sender.sendMessage(TextFormat.GREEN + "Дроп-пати остановлен!");
        return true;
    }

    private boolean handleSetZone(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("dp.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (args.length < 2) {
            player.sendMessage(TextFormat.RED + "/dp setzone <pos1|pos2>");
            return true;
        }
        Config config = getConfig();
        String key = args[1].equalsIgnoreCase("pos1") ? "zone.pos1" : "zone.pos2";
        config.set(key + ".world", player.getLevel().getName());
        config.set(key + ".x", player.getX());
        config.set(key + ".y", player.getY());
        config.set(key + ".z", player.getZ());
        config.save();
        player.sendMessage(TextFormat.GREEN + args[1].toUpperCase() + " установлена!");
        return true;
    }

    private boolean handleTop(CommandSender sender) {
        if (playerPickups.isEmpty()) {
            sender.sendMessage(TextFormat.YELLOW + "Нет данных.");
            return true;
        }
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(playerPickups.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        sender.sendMessage(TextFormat.GOLD + "=== Топ сборщиков ===");
        int rank = 1;
        for (Map.Entry<String, Integer> entry : sorted) {
            if (rank > 10) break;
            String medal = rank == 1 ? "§6★" : rank == 2 ? "§7★" : rank == 3 ? "§c★" : "§7 ";
            sender.sendMessage(medal + " #" + rank + " " + entry.getKey()
                    + " §7— §e" + entry.getValue() + " предметов");
            rank++;
        }
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("dp.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        sender.sendMessage(TextFormat.GREEN + "DropParty перезагружен!");
        return true;
    }

    private void startParty() {
        partyActive = true;
        playerPickups.clear();
        partyTimer = getConfig().getInt("settings.duration", 300);
        int dropInterval = getConfig().getInt("settings.drop-interval", 2);

        getServer().broadcastMessage(msg("party-started")
                .replace("{time}", String.valueOf(partyTimer / 60)));

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(TextFormat.GOLD + "ДРОП-ПАТИ!",
                    TextFormat.YELLOW + "Предметы падают с неба! Собирайте!", 10, 60, 10);
        }

        dropTaskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (!partyActive) {
                    this.getHandler().cancel();
                    return;
                }
                dropItems();
            }
        }, dropInterval * 20).getTaskId();

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (partyTimer <= 0) {
                    endParty();
                    this.getHandler().cancel();
                    return;
                }
                if (partyTimer == 60 || partyTimer == 30 || partyTimer == 10) {
                    getServer().broadcastMessage(msg("time-remaining")
                            .replace("{time}", String.valueOf(partyTimer)));
                }
                partyTimer--;
            }
        }, 20).getTaskId();
    }

    private void dropItems() {
        Config config = getConfig();
        double x1 = Math.min(config.getDouble("zone.pos1.x"), config.getDouble("zone.pos2.x"));
        double x2 = Math.max(config.getDouble("zone.pos1.x"), config.getDouble("zone.pos2.x"));
        double z1 = Math.min(config.getDouble("zone.pos1.z"), config.getDouble("zone.pos2.z"));
        double z2 = Math.max(config.getDouble("zone.pos1.z"), config.getDouble("zone.pos2.z"));
        double dropHeight = config.getDouble("settings.drop-height", 30);
        double baseY = Math.max(config.getDouble("zone.pos1.y"), config.getDouble("zone.pos2.y"));
        String worldName = config.getString("zone.pos1.world", "world");

        Level level = getServer().getLevelByName(worldName);
        if (level == null) return;

        int itemsPerDrop = config.getInt("settings.items-per-drop", 5);
        List<Item> lootTable = buildLootTable();
        if (lootTable.isEmpty()) return;

        for (int i = 0; i < itemsPerDrop; i++) {
            double x = x1 + random.nextDouble() * (x2 - x1);
            double z = z1 + random.nextDouble() * (z2 - z1);
            double y = baseY + dropHeight;

            Item item = lootTable.get(random.nextInt(lootTable.size())).clone();
            dropItemAt(level, x, y, z, item);
        }
    }

    private void dropItemAt(Level level, double x, double y, double z, Item item) {
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
                        .add(new FloatTag(0)))
                .putShort("Health", 5)
                .putCompound("Item", NBTIO.putItemHelper(item))
                .putShort("PickupDelay", 10);

        EntityItem entityItem = new EntityItem(
                level.getChunk((int) x >> 4, (int) z >> 4), nbt);
        entityItem.spawnToAll();
    }

    private List<Item> buildLootTable() {
        List<Item> items = new ArrayList<>();
        Config config = getConfig();
        if (!config.exists("loot-table")) {
            items.add(Item.get(Item.DIAMOND, 0, 1));
            items.add(Item.get(Item.IRON_INGOT, 0, 3));
            items.add(Item.get(Item.GOLD_INGOT, 0, 2));
            items.add(Item.get(Item.EMERALD, 0, 1));
            items.add(Item.get(Item.APPLE, 0, 5));
            return items;
        }

        for (String key : config.getSection("loot-table").getKeys(false)) {
            ConfigSection itemSection = config.getSection("loot-table." + key);
            int id = itemSection.getInt("id", 1);
            int damage = itemSection.getInt("damage", 0);
            int count = itemSection.getInt("count", 1);
            int weight = itemSection.getInt("weight", 1);
            Item item = Item.get(id, damage, count);
            for (int i = 0; i < weight; i++) {
                items.add(item);
            }
        }
        return items;
    }

    public void onPlayerPickup(Player player) {
        if (!partyActive) return;
        playerPickups.merge(player.getName(), 1, Integer::sum);
    }

    private void endParty() {
        partyActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        if (dropTaskId != -1) {
            getServer().getScheduler().cancelTask(dropTaskId);
            dropTaskId = -1;
        }

        getServer().broadcastMessage(msg("party-ended"));

        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(playerPickups.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));

        if (!sorted.isEmpty()) {
            getServer().broadcastMessage(TextFormat.GOLD + "=== Результаты Дроп-Пати ===");
            int rank = 1;
            for (Map.Entry<String, Integer> entry : sorted) {
                if (rank > 5) break;
                String medal = rank == 1 ? "§6★" : rank == 2 ? "§7★" : rank == 3 ? "§c★" : "§7 ";
                getServer().broadcastMessage(medal + " #" + rank + " " + entry.getKey()
                        + " §7— §e" + entry.getValue() + " предметов");
                rank++;
            }
        }
    }

    public void stopParty() {
        partyActive = false;
        if (taskId != -1) {
            getServer().getScheduler().cancelTask(taskId);
            taskId = -1;
        }
        if (dropTaskId != -1) {
            getServer().getScheduler().cancelTask(dropTaskId);
            dropTaskId = -1;
        }
    }

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        return TextFormat.colorize(msgConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public boolean isPartyActive() { return partyActive; }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== DropParty ===");
        sender.sendMessage(TextFormat.YELLOW + "/dp top" + TextFormat.GRAY + " — Топ сборщиков");
        if (sender.hasPermission("dp.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/dp start" + TextFormat.GRAY + " — Начать дроп-пати");
            sender.sendMessage(TextFormat.YELLOW + "/dp stop" + TextFormat.GRAY + " — Остановить");
            sender.sendMessage(TextFormat.YELLOW + "/dp setzone <pos1|pos2>" + TextFormat.GRAY + " — Задать зону дропа");
            sender.sendMessage(TextFormat.YELLOW + "/dp reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
