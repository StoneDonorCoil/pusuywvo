package com.mcevents.luckyblocks;

import cn.nukkit.item.Item;
import cn.nukkit.potion.Effect;

public class LuckyResult {

    public enum Type {
        ITEM, EFFECT, EXPLOSION, MOB_SPAWN, NOTHING
    }

    private final String message;
    private final String shortMessage;
    private final int points;
    private final Type type;
    private Item item;
    private Effect effect;

    public LuckyResult(String message, String shortMessage, int points, Type type) {
        this.message = message;
        this.shortMessage = shortMessage;
        this.points = points;
        this.type = type;
    }

    public LuckyResult(String message, String shortMessage, int points, Type type, Item item) {
        this(message, shortMessage, points, type);
        this.item = item;
    }

    public LuckyResult(String message, String shortMessage, int points, Type type, Effect effect) {
        this(message, shortMessage, points, type);
        this.effect = effect;
    }

    public String getMessage() {
        return message;
    }

    public String getShortMessage() {
        return shortMessage;
    }

    public int getPoints() {
        return points;
    }

    public Type getType() {
        return type;
    }

    public Item getItem() {
        return item;
    }

    public Effect getEffect() {
        return effect;
    }
}
