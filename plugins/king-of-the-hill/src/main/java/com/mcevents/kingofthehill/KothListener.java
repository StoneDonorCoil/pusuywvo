package com.mcevents.kingofthehill;

import cn.nukkit.event.EventHandler;
import cn.nukkit.event.Listener;
import cn.nukkit.event.player.PlayerQuitEvent;

public class KothListener implements Listener {

    private final KothPlugin plugin;

    public KothListener(KothPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        plugin.getParticipants().remove(event.getPlayer().getName());
    }
}
