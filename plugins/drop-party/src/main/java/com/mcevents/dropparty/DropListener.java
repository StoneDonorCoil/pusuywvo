package com.mcevents.dropparty;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.Listener;
import cn.nukkit.event.inventory.InventoryPickupItemEvent;

public class DropListener implements Listener {

    private final DropPartyPlugin plugin;

    public DropListener(DropPartyPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onPickupItem(InventoryPickupItemEvent event) {
        if (!plugin.isPartyActive()) return;
        if (event.getInventory().getHolder() instanceof Player player) {
            plugin.onPlayerPickup(player);
        }
    }
}
