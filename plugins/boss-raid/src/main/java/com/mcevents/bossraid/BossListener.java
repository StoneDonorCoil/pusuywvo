package com.mcevents.bossraid;

import cn.nukkit.Player;
import cn.nukkit.event.EventHandler;
import cn.nukkit.event.EventPriority;
import cn.nukkit.event.Listener;
import cn.nukkit.event.entity.EntityDamageByEntityEvent;
import cn.nukkit.event.entity.EntityDamageEvent;

public class BossListener implements Listener {

    private final BossRaidPlugin plugin;

    public BossListener(BossRaidPlugin plugin) {
        this.plugin = plugin;
    }

    @EventHandler(priority = EventPriority.HIGH)
    public void onEntityDamage(EntityDamageEvent event) {
        if (!plugin.isRaidActive()) return;
        if (plugin.getBossEntity() == null) return;
        if (event.getEntity().getId() != plugin.getBossEntity().getId()) return;

        event.setCancelled(true);

        if (event instanceof EntityDamageByEntityEvent damageEvent) {
            if (damageEvent.getDamager() instanceof Player attacker) {
                plugin.onBossDamage(attacker, event.getDamage());
            }
        }
    }
}
