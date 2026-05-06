package com.mcevents.spleef;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.Listener;
import cn.nukkit.event.block.BlockBreakEvent;
import cn.nukkit.event.player.PlayerMoveEvent;
import cn.nukkit.event.player.PlayerQuitEvent;

public class SpleefListener implements Listener {

    private final SpleefPlugin plugin;

    public SpleefListener(SpleefPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onBlockBreak(BlockBreakEvent event) {
        Player player = event.getPlayer();
        if (!plugin.getGamePlayers().contains(player.getName())) return;
        if (plugin.getState() != SpleefPlugin.GameState.INGAME) {
            event.setCancelled(true);
            return;
        }
        if (!plugin.getAlivePlayers().contains(player.getName())) {
            event.setCancelled(true);
        }
        event.setDrops(new cn.nukkit.item.Item[0]);
    }

    @EventHandler
    public void onPlayerMove(PlayerMoveEvent event) {
        if (plugin.getState() != SpleefPlugin.GameState.INGAME) return;
        plugin.checkFallenPlayers();
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        if (plugin.getGamePlayers().contains(event.getPlayer().getName())) {
            plugin.getGamePlayers().remove(event.getPlayer().getName());
            plugin.getAlivePlayers().remove(event.getPlayer().getName());
        }
    }
}
