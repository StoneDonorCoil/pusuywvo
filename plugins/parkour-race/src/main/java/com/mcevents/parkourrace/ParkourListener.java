package com.mcevents.parkourrace;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.Listener;
import cn.nukkit.event.player.PlayerMoveEvent;
import cn.nukkit.event.player.PlayerQuitEvent;
import cn.nukkit.level.Position;

import java.util.List;

public class ParkourListener implements Listener {

    private final ParkourRacePlugin plugin;
    private static final double CHECK_RADIUS = 2.5;

    public ParkourListener(ParkourRacePlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler
    public void onPlayerMove(PlayerMoveEvent event) {
        if (!plugin.isRaceActive()) return;
        Player player = event.getPlayer();
        if (!plugin.getParticipants().contains(player.getName())) return;

        List<Position> checkpoints = plugin.getCheckpoints();
        for (int i = 0; i < checkpoints.size(); i++) {
            Position cp = checkpoints.get(i);
            if (cp.getLevel() != null && cp.getLevel().getName().equals(player.getLevel().getName())) {
                if (player.getPosition().distance(cp) <= CHECK_RADIUS) {
                    plugin.onPlayerReachCheckpoint(player, i + 1);
                }
            }
        }

        Position finish = plugin.getFinishPosition();
        if (finish != null && finish.getLevel() != null
                && finish.getLevel().getName().equals(player.getLevel().getName())
                && player.getPosition().distance(finish) <= CHECK_RADIUS) {
            plugin.onPlayerFinish(player);
        }
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        plugin.getParticipants().remove(event.getPlayer().getName());
    }
}
