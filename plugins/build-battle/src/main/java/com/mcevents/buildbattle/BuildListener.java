package com.mcevents.buildbattle;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.Listener;
import cn.nukkit.event.block.BlockBreakEvent;
import cn.nukkit.event.block.BlockPlaceEvent;
import cn.nukkit.event.player.PlayerQuitEvent;

public class BuildListener implements Listener {

    private final BuildBattlePlugin plugin;

    public BuildListener(BuildBattlePlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onBlockPlace(BlockPlaceEvent event) {
        Player player = event.getPlayer();
        if (!plugin.getParticipants().contains(player.getName())) return;
        if (plugin.getState() != BuildBattlePlugin.GameState.BUILDING) {
            event.setCancelled(true);
        }
    }

    @EventHandler
    public void onBlockBreak(BlockBreakEvent event) {
        Player player = event.getPlayer();
        if (!plugin.getParticipants().contains(player.getName())) return;
        if (plugin.getState() != BuildBattlePlugin.GameState.BUILDING) {
            event.setCancelled(true);
        }
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        plugin.getParticipants().remove(event.getPlayer().getName());
    }
}
