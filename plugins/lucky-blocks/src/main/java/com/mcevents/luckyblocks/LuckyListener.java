package com.mcevents.luckyblocks;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.Listener;
import cn.nukkit.event.block.BlockBreakEvent;

public class LuckyListener implements Listener {

    private final LuckyBlocksPlugin plugin;

    public LuckyListener(LuckyBlocksPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onBlockBreak(BlockBreakEvent event) {
        if (!plugin.isEventActive()) return;
        Player player = event.getPlayer();
        if (!plugin.getParticipants().contains(player.getName())) return;

        if (event.getBlock().getId() == plugin.getLuckyBlockId()) {
            event.setCancelled(true);
            event.getBlock().getLevel().setBlock(event.getBlock(), cn.nukkit.block.Block.get(cn.nukkit.block.Block.AIR));
            plugin.onLuckyBlockBreak(player, event.getBlock());
        }
    }
}
