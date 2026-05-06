package com.mcevents.survivalgames;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.EventPriority;
import cn.nukkit.event.Listener;
import cn.nukkit.event.entity.EntityDamageByEntityEvent;
import cn.nukkit.event.entity.EntityDamageEvent;
import cn.nukkit.event.player.PlayerDropItemEvent;
import cn.nukkit.event.player.PlayerQuitEvent;

public class GameListener implements Listener {

    private final SurvivalGamesPlugin plugin;

    public GameListener(SurvivalGamesPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.HIGH)
    public void onPlayerDamage(EntityDamageEvent event) {
        if (!(event.getEntity() instanceof Player victim)) return;

        String arenaName = plugin.getPlayerArenaMap().get(victim.getName());
        if (arenaName == null) return;

        GameArena arena = plugin.getArenas().get(arenaName);
        if (arena == null) return;

        if (arena.getState() == GameArena.ArenaState.WAITING
                || arena.getState() == GameArena.ArenaState.STARTING) {
            event.setCancelled(true);
            return;
        }

        if (!arena.isAlive(victim.getName())) {
            event.setCancelled(true);
            return;
        }

        if (victim.getHealth() - event.getFinalDamage() <= 0) {
            event.setCancelled(true);
            Player killer = null;
            if (event instanceof EntityDamageByEntityEvent damageByEntity) {
                if (damageByEntity.getDamager() instanceof Player) {
                    killer = (Player) damageByEntity.getDamager();
                }
            }
            arena.onPlayerDeath(victim, killer);
        }
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        Player player = event.getPlayer();
        String arenaName = plugin.getPlayerArenaMap().get(player.getName());
        if (arenaName == null) return;

        GameArena arena = plugin.getArenas().get(arenaName);
        if (arena != null) {
            arena.removePlayer(player);
        }
    }

    @EventHandler
    public void onItemDrop(PlayerDropItemEvent event) {
        String arenaName = plugin.getPlayerArenaMap().get(event.getPlayer().getName());
        if (arenaName != null) {
            GameArena arena = plugin.getArenas().get(arenaName);
            if (arena != null && (arena.getState() == GameArena.ArenaState.WAITING
                    || arena.getState() == GameArena.ArenaState.STARTING)) {
                event.setCancelled(true);
            }
        }
    }
}
