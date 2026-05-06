package com.mcevents.buildbattle;

import cn.nukkit.level.Position;

public class BuildPlot {

    private final String ownerName;
    private final Position position;

    public BuildPlot(String ownerName, Position position) {
        this.ownerName = ownerName;
        this.position = position;
    }

    public String getOwnerName() {
        return ownerName;
    }

    public Position getPosition() {
        return position;
    }
}
