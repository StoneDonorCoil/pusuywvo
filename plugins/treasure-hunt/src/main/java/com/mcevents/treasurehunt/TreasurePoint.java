package com.mcevents.treasurehunt;

import cn.nukkit.math.Vector3;

import java.util.Objects;

public class TreasurePoint {

    private final String name;
    private final double x;
    private final double y;
    private final double z;
    private final String worldName;
    private final int tier;

    public TreasurePoint(String name, double x, double y, double z, String worldName, int tier) {
        this.name = name;
        this.x = x;
        this.y = y;
        this.z = z;
        this.worldName = worldName;
        this.tier = tier;
    }

    public String getName() {
        return name;
    }

    public double getX() {
        return x;
    }

    public double getY() {
        return y;
    }

    public double getZ() {
        return z;
    }

    public String getWorldName() {
        return worldName;
    }

    public int getTier() {
        return tier;
    }

    public Vector3 toVector3() {
        return new Vector3(x, y, z);
    }

    public double distanceTo(Vector3 other) {
        return toVector3().distance(other);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        TreasurePoint that = (TreasurePoint) o;
        return Double.compare(that.x, x) == 0
                && Double.compare(that.y, y) == 0
                && Double.compare(that.z, z) == 0
                && Objects.equals(worldName, that.worldName);
    }

    @Override
    public int hashCode() {
        return Objects.hash(x, y, z, worldName);
    }
}
