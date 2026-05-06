package com.mcevents.mobarena;

import cn.nukkit.Player;
import cn.nukkit.entity.Entity;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.EventPriority;
import cn.nukkit.event.Listener;
import cn.nukkit.event.entity.EntityDamageByEntityEvent;
import cn.nukkit.event.entity.EntityDamageEvent;
import cn.nukkit.event.entity.EntityDeathEvent;
import cn.nukkit.event.player.PlayerQuitEvent;

public class ArenaListener implements Listener {

    private final MobArenaPlugin plugin;

    public ArenaListener(MobArenaPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.HIGH)
    public void onEntityDeath(EntityDeathEvent event) {
        if (!plugin.isArenaActive()) return;
        Entity entity = event.getEntity();
        if (!plugin.getSpawnedMobs().contains(entity)) return;

        Player killer = null;
        if (entity.getLastDamageCause() instanceof EntityDamageByEntityEvent damageEvent) {
            if (damageEvent.getDamager() instanceof Player) {
                killer = (Player) damageEvent.getDamager();
            }
        }
        plugin.onMobKilled(killer, entity);
    }

    @EventHandler(priority = EventPriority.HIGH)
    public void onPlayerDamage(EntityDamageEvent event) {
        if (!(event.getEntity() instanceof Player player)) return;
        if (!plugin.isArenaActive()) return;
        if (!plugin.getAlivePlayers().contains(player.getName())) return;

        if (player.getHealth() - event.getFinalDamage() <= 0) {
            event.setCancelled(true);
            plugin.onPlayerDeath(player);
        }
    }

    @EventHandler
    public void onPlayerQuit(PlayerQuitEvent event) {
        if (plugin.getPlayers().contains(event.getPlayer().getName())) {
            plugin.getPlayers().remove(event.getPlayer().getName());
            plugin.getAlivePlayers().remove(event.getPlayer().getName());
        }
    }
}
