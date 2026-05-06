package com.mcevents.luckyblocks;

import cn.nukkit.Player;
import cn.nukkit.block.Block;
import cn.nukkit.command.Command;
import cn.nukkit.command.CommandSender;
import cn.nukkit.entity.Entity;
import cn.nukkit.item.Item;
import cn.nukkit.level.Position;
import cn.nukkit.nbt.tag.CompoundTag;
import cn.nukkit.nbt.tag.DoubleTag;
import cn.nukkit.nbt.tag.FloatTag;
import cn.nukkit.nbt.tag.ListTag;
import cn.nukkit.plugin.PluginBase;
import cn.nukkit.potion.Effect;
import cn.nukkit.scheduler.Task;
import cn.nukkit.utils.Config;
import cn.nukkit.utils.TextFormat;

import java.util.*;

public class LuckyBlocksPlugin extends PluginBase {

    private boolean eventActive = false;
    private int luckyBlockId;
    private final Set<String> participants = new HashSet<>();
    private final Map<String, Integer> playerScores = new HashMap<>();
    private int eventTimer;
    private int taskId = -1;
    private final Random random = new Random();

    @Override
    public void onEnable() {
        saveDefaultConfig();
        saveResource("messages.yml", false);
        luckyBlockId = getConfig().getInt("settings.lucky-block-id", Block.SPONGE);
        getServer().getPluginManager().registerEvents(new LuckyListener(this), this);
        getLogger().info(TextFormat.GREEN + "LuckyBlocks загружен! ID блока: " + luckyBlockId);
    }

    @Override
    public void onDisable() {
        stopEvent();
    }

    @Override
    public boolean onCommand(CommandSender sender, Command command, String label, String[] args) {
        if (!command.getName().equalsIgnoreCase("lb")) return false;
        if (args.length == 0) {
            sendHelp(sender);
            return true;
        }

        switch (args[0].toLowerCase()) {
            case "start":
                return handleStart(sender);
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
            case "place":
                return handlePlace(sender, args);
            case "reload":
                return handleReload(sender);
            default:
                sendHelp(sender);
                return true;
        }
    }

    private boolean handleStart(CommandSender sender) {
        if (!sender.hasPermission("lb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        if (eventActive) {
            sender.sendMessage(TextFormat.RED + "Ивент уже идёт!");
            return true;
        }
        startEvent();
        return true;
    }

    private boolean handleStop(CommandSender sender) {
        if (!sender.hasPermission("lb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        stopEvent();
        sender.sendMessage(TextFormat.GREEN + "LuckyBlocks остановлен!");
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
        playerScores.putIfAbsent(player.getName(), 0);
        player.sendMessage(msg("joined"));
        return true;
    }

    private boolean handleLeave(CommandSender sender) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        participants.remove(player.getName());
        player.sendMessage(msg("left"));
        return true;
    }

    private boolean handleScore(CommandSender sender) {
        if (!(sender instanceof Player player)) return true;
        int score = playerScores.getOrDefault(player.getName(), 0);
        player.sendMessage(TextFormat.GOLD + "Ваш счёт: " + TextFormat.WHITE + score);
        return true;
    }

    private boolean handleTop(CommandSender sender) {
        List<Map.Entry<String, Integer>> sorted = new ArrayList<>(playerScores.entrySet());
        sorted.sort((a, b) -> b.getValue().compareTo(a.getValue()));
        sender.sendMessage(TextFormat.GOLD + "=== Топ LuckyBlocks ===");
        int rank = 1;
        for (Map.Entry<String, Integer> entry : sorted) {
            if (rank > 10) break;
            sender.sendMessage(TextFormat.YELLOW + "#" + rank + " " + entry.getKey()
                    + TextFormat.GRAY + " — " + TextFormat.WHITE + entry.getValue());
            rank++;
        }
        return true;
    }

    private boolean handlePlace(CommandSender sender, String[] args) {
        if (!(sender instanceof Player player)) {
            sender.sendMessage(msg("only-players"));
            return true;
        }
        if (!sender.hasPermission("lb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        int count = args.length >= 2 ? parseInt(args[1], 1) : 1;
        int placed = 0;
        for (int i = 0; i < count; i++) {
            int offsetX = random.nextInt(41) - 20;
            int offsetZ = random.nextInt(41) - 20;
            int x = (int) player.getX() + offsetX;
            int z = (int) player.getZ() + offsetZ;
            int y = player.getLevel().getHighestBlockAt(x, z) + 1;
            player.getLevel().setBlock(new Position(x, y, z, player.getLevel()), Block.get(luckyBlockId));
            placed++;
        }
        player.sendMessage(TextFormat.GREEN + "Размещено " + placed + " лаки-блоков!");
        return true;
    }

    private boolean handleReload(CommandSender sender) {
        if (!sender.hasPermission("lb.admin")) {
            sender.sendMessage(msg("no-permission"));
            return true;
        }
        reloadConfig();
        luckyBlockId = getConfig().getInt("settings.lucky-block-id", Block.SPONGE);
        sender.sendMessage(TextFormat.GREEN + "LuckyBlocks перезагружен!");
        return true;
    }

    private void startEvent() {
        eventActive = true;
        participants.clear();
        playerScores.clear();
        eventTimer = getConfig().getInt("settings.event-duration", 900);

        getServer().broadcastMessage(msg("event-started")
                .replace("{time}", String.valueOf(eventTimer / 60)));

        for (Player player : getServer().getOnlinePlayers().values()) {
            player.sendTitle(TextFormat.GOLD + "ЛАКИ-БЛОКИ!",
                    TextFormat.YELLOW + "/lb join", 10, 60, 10);
        }

        taskId = getServer().getScheduler().scheduleRepeatingTask(this, new Task() {
            @Override
            public void onRun(int currentTick) {
                if (eventTimer <= 0) {
                    endEvent();
                    this.getHandler().cancel();
                    return;
                }
                if (eventTimer == 60 || eventTimer == 30 || eventTimer == 10) {
                    broadcastToParticipants(msg("time-remaining")
                            .replace("{time}", String.valueOf(eventTimer)));
                }
                eventTimer--;
            }
        }, 20).getTaskId();
    }

    public void onLuckyBlockBreak(Player player, Block block) {
        if (!eventActive) return;
        if (!participants.contains(player.getName())) return;

        LuckyResult result = generateResult();
        applyResult(player, result, block.getLocation());

        playerScores.merge(player.getName(), result.getPoints(), Integer::sum);

        player.sendMessage(result.getMessage());
        if (result.getPoints() > 0) {
            player.sendTitle("", result.getShortMessage(), 5, 20, 5);
        }
    }

    private LuckyResult generateResult() {
        int roll = random.nextInt(100);
        Config config = getConfig();

        int goodChance = config.getInt("settings.good-chance", 45);
        int badChance = config.getInt("settings.bad-chance", 30);

        if (roll < goodChance) {
            return generateGoodResult();
        } else if (roll < goodChance + badChance) {
            return generateBadResult();
        } else {
            return generateNeutralResult();
        }
    }

    private LuckyResult generateGoodResult() {
        int type = random.nextInt(6);
        return switch (type) {
            case 0 -> new LuckyResult(
                    TextFormat.GREEN + "Вам выпал алмазный меч!",
                    TextFormat.GREEN + "Алмазный меч!",
                    10, LuckyResult.Type.ITEM, Item.get(Item.DIAMOND_SWORD));
            case 1 -> new LuckyResult(
                    TextFormat.GREEN + "Вам выпали алмазы!",
                    TextFormat.GREEN + "Алмазы!",
                    15, LuckyResult.Type.ITEM, Item.get(Item.DIAMOND, 0, 3 + random.nextInt(5)));
            case 2 -> new LuckyResult(
                    TextFormat.GREEN + "Золотое яблоко!",
                    TextFormat.GREEN + "Золотое яблоко!",
                    20, LuckyResult.Type.ITEM, Item.get(Item.GOLDEN_APPLE, 0, 1 + random.nextInt(3)));
            case 3 -> new LuckyResult(
                    TextFormat.AQUA + "Эффект скорости!",
                    TextFormat.AQUA + "Скорость!",
                    5, LuckyResult.Type.EFFECT, Effect.getEffect(Effect.SPEED).setDuration(600).setAmplifier(1));
            case 4 -> new LuckyResult(
                    TextFormat.GREEN + "Алмазная броня!",
                    TextFormat.GREEN + "Броня!",
                    25, LuckyResult.Type.ITEM, Item.get(Item.DIAMOND_CHESTPLATE));
            default -> new LuckyResult(
                    TextFormat.GREEN + "Набор еды!",
                    TextFormat.GREEN + "Еда!",
                    5, LuckyResult.Type.ITEM, Item.get(Item.STEAK, 0, 16));
        };
    }

    private LuckyResult generateBadResult() {
        int type = random.nextInt(5);
        return switch (type) {
            case 0 -> new LuckyResult(
                    TextFormat.RED + "Взрыв!",
                    TextFormat.RED + "БУМ!",
                    -10, LuckyResult.Type.EXPLOSION);
            case 1 -> new LuckyResult(
                    TextFormat.RED + "Отравление!",
                    TextFormat.RED + "Яд!",
                    -5, LuckyResult.Type.EFFECT, Effect.getEffect(Effect.POISON).setDuration(200).setAmplifier(0));
            case 2 -> new LuckyResult(
                    TextFormat.RED + "Спавн мобов!",
                    TextFormat.RED + "Мобы!",
                    -8, LuckyResult.Type.MOB_SPAWN);
            case 3 -> new LuckyResult(
                    TextFormat.RED + "Медлительность!",
                    TextFormat.RED + "Медлительность!",
                    -3, LuckyResult.Type.EFFECT, Effect.getEffect(Effect.SLOWNESS).setDuration(400).setAmplifier(1));
            default -> new LuckyResult(
                    TextFormat.RED + "Слабость!",
                    TextFormat.RED + "Слабость!",
                    -5, LuckyResult.Type.EFFECT, Effect.getEffect(Effect.WEAKNESS).setDuration(300).setAmplifier(0));
        };
    }

    private LuckyResult generateNeutralResult() {
        int type = random.nextInt(3);
        return switch (type) {
            case 0 -> new LuckyResult(
                    TextFormat.YELLOW + "Ничего не произошло...",
                    TextFormat.YELLOW + "Пусто",
                    0, LuckyResult.Type.NOTHING);
            case 1 -> new LuckyResult(
                    TextFormat.YELLOW + "Несколько палок...",
                    TextFormat.YELLOW + "Палки",
                    1, LuckyResult.Type.ITEM, Item.get(Item.STICK, 0, 4));
            default -> new LuckyResult(
                    TextFormat.YELLOW + "Немного опыта!",
                    TextFormat.YELLOW + "XP",
                    2, LuckyResult.Type.NOTHING);
        };
    }

    private void applyResult(Player player, LuckyResult result, Position pos) {
        switch (result.getType()) {
            case ITEM:
                if (result.getItem() != null) {
                    player.getInventory().addItem(result.getItem());
                }
                break;
            case EFFECT:
                if (result.getEffect() != null) {
                    player.addEffect(result.getEffect());
                }
                break;
            case EXPLOSION:
                float explosionPower = getConfig().getInt("settings.explosion-power", 3);
                pos.getLevel().createExplosion(pos, explosionPower, null, false, true);
                break;
            case MOB_SPAWN:
                spawnHostileMobs(pos, 3);
                break;
            case NOTHING:
                break;
        }
    }

    private void spawnHostileMobs(Position pos, int count) {
        String[] mobTypes = {"Zombie", "Skeleton", "Spider"};
        for (int i = 0; i < count; i++) {
            String type = mobTypes[random.nextInt(mobTypes.length)];
            CompoundTag nbt = new CompoundTag()
                    .putList("Pos", new ListTag<DoubleTag>()
                            .add(new DoubleTag(pos.getX() + random.nextInt(5) - 2))
                            .add(new DoubleTag(pos.getY()))
                            .add(new DoubleTag(pos.getZ() + random.nextInt(5) - 2)))
                    .putList("Motion", new ListTag<DoubleTag>()
                            .add(new DoubleTag(0)).add(new DoubleTag(0)).add(new DoubleTag(0)))
                    .putList("Rotation", new ListTag<FloatTag>()
                            .add(new FloatTag(0)).add(new FloatTag(0)));

            Entity entity = Entity.createEntity(type,
                    pos.getLevel().getChunk((int) pos.getX() >> 4, (int) pos.getZ() >> 4), nbt);
            if (entity != null) entity.spawnToAll();
        }
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
            getServer().broadcastMessage(TextFormat.GOLD + "=== Результаты LuckyBlocks ===");
            int rank = 1;
            for (Map.Entry<String, Integer> entry : sorted) {
                if (rank > 5) break;
                String medal = rank == 1 ? "§6★" : rank == 2 ? "§7★" : rank == 3 ? "§c★" : "§7 ";
                getServer().broadcastMessage(medal + " #" + rank + " " + entry.getKey()
                        + " §7— §e" + entry.getValue() + " очков");
                rank++;
            }
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
            if (player != null) player.sendMessage(message);
        }
    }

    private int parseInt(String s, int def) {
        try { return Integer.parseInt(s); } catch (NumberFormatException e) { return def; }
    }

    public String msg(String key) {
        Config msgConfig = new Config(getDataFolder() + "/messages.yml", Config.YAML);
        return TextFormat.colorize(msgConfig.getString(key, "&cСообщение не найдено: " + key));
    }

    public boolean isEventActive() { return eventActive; }
    public int getLuckyBlockId() { return luckyBlockId; }
    public Set<String> getParticipants() { return participants; }

    private void sendHelp(CommandSender sender) {
        sender.sendMessage(TextFormat.GOLD + "=== LuckyBlocks ===");
        sender.sendMessage(TextFormat.YELLOW + "/lb join" + TextFormat.GRAY + " — Присоединиться");
        sender.sendMessage(TextFormat.YELLOW + "/lb leave" + TextFormat.GRAY + " — Покинуть");
        sender.sendMessage(TextFormat.YELLOW + "/lb score" + TextFormat.GRAY + " — Ваш счёт");
        sender.sendMessage(TextFormat.YELLOW + "/lb top" + TextFormat.GRAY + " — Таблица лидеров");
        if (sender.hasPermission("lb.admin")) {
            sender.sendMessage(TextFormat.YELLOW + "/lb start" + TextFormat.GRAY + " — Начать ивент");
            sender.sendMessage(TextFormat.YELLOW + "/lb stop" + TextFormat.GRAY + " — Остановить");
            sender.sendMessage(TextFormat.YELLOW + "/lb place [кол-во]" + TextFormat.GRAY + " — Разместить лаки-блоки");
            sender.sendMessage(TextFormat.YELLOW + "/lb reload" + TextFormat.GRAY + " — Перезагрузить");
        }
    }
}
