package com.mcevents.treasurehunt;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.Listener;
import cn.nukkit.event.player.PlayerMoveEvent;

public class TreasureListener implements Listener {

    private final TreasureHuntPlugin plugin;
    private static final double FIND_RADIUS = 3.0;

    public TreasureListener(TreasureHuntPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onPlayerMove(PlayerMoveEvent event) {
        if (!plugin.isEventActive()) return;

        Player player = event.getPlayer();
        if (!player.getLevel().getName().equals(event.getTo().getLevel().getName())) return;

        for (TreasurePoint tp : plugin.getTreasures().values()) {
            if (!tp.getWorldName().equals(player.getLevel().getName())) continue;
            if (tp.distanceTo(player.getPosition()) <= FIND_RADIUS) {
                plugin.onPlayerFoundTreasure(player, tp);
            }
        }
    }
}
