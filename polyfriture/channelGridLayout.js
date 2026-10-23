.pragma library

// Coordinates start at the bottom left. Balance column populations before
// assigning channels, keeping every bottom and left boundary populated.
function placements(channelCount, configuredColumns, transposed) {
    if (channelCount <= 0)
        return [];
    var columns = Math.min(channelCount, Math.max(1, configuredColumns));
    var shortHeight = Math.floor(channelCount / columns);
    var tallColumns = channelCount % columns;
    var result = [];
    for (var column = 0; column < columns; ++column) {
        var height = shortHeight + (column < tallColumns ? 1 : 0);
        for (var row = 0; row < height; ++row)
            result.push(transposed
                ? {column: row, rowFromBottom: column}
                : {column: column, rowFromBottom: row});
    }
    return result;
}
