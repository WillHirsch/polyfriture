# Channel configuration and reset lifecycle

Capture uses one input device at 48 kHz. The backend records all of that
device's physical input channels, then routes the selected subset into arrays
with shape `(channels, samples)`. There is no application channel-count limit.

`ChannelConfiguration` is immutable. `device_id` is the PortAudio device index
for this process, and `channel_ids` contains unique zero-based physical input
indices in ascending order. `device_channel_count` is the device's physical
input capacity; the selected row count is `len(channel_ids)`.
Array row `i` belongs to `channel_ids[i]`.
`channel_labels` uses one-based names, such as `Channel 2` for physical index 1.
Device indices are runtime identities, not persistent identifiers across
application launches.

`AudioBackend().select_channels(ids)` accepts a nonempty subset, normalizes
order and duplicates, and rejects noninteger or out-of-range IDs. It raises
`ValueError` without changing capture on invalid input or when no device is
configured. The settings dialog presents a scrollable checklist for the active
device and prevents unchecking its last selected channel. The same ordered
subset reaches every input visualization; Scope overlays its channels and
triggers from the first selected physical input.

Saved profiles contain the requested raw device name, host API and selected
physical IDs. Device order, default markers and channel-count changes do not
change that identity. A missing or ambiguous device keeps the active fallback;
missing channels use the available subset, or Channel 1 if none remain.
The dialog explains the fallback and preserves the requested profile until
an explicit device or channel choice replaces it. Device discovery happens at
startup, so reconnecting an unavailable device requires restarting the app.
Schema upgrades convert the legacy single/dual pair for both existing profiles
and the one-time, read-only import from Friture.

## A configuration boundary

Each effective selection or device change creates a strictly newer
`generation`. Re-selecting the same subset or device is a no-op for capture;
explicitly choosing the active fallback still adopts it as the saved request.
Startup without an available device has no configuration and leaves the
settings dialog available for choosing a usable input.

Changes happen on the GUI thread, in this order:

1. Prepare and, when running, start a candidate device stream. Failed open or
   start leaves the previous stream, channel choices and generation intact.
   Successfully replaced streams are stopped and closed. A paused input stays
   paused, including after device replacement.
2. Discard pending capture samples and publish `configuration_changed`.
3. `AudioBuffer` clears sample history, cursor and timing metadata, then emits
   its own `configuration_changed`. Each input panel clears mutable processor
   state and displayed history while retaining its parameters and pause state.
   This includes same-count channel replacements and changes of device.
4. New audio carries its generation. `AudioBuffer` accepts only the active
   generation, rejecting delayed old data or data whose configuration has not
   arrived. Consumers receive data only after the reset notification.

Ordinary pause/resume does not create a new configuration or clear analysis
history. Input reconfiguration does not restart Generator output. Closed or
replaced panels disconnect both data and configuration subscriptions.

## Panel contract

A panel has one shared set of analysis and display parameters for all selected
channels. Each channel owns its mutable processing
state: filter overlaps, smoothing, peaks, cursors and histories. A setting
change applies uniformly to every channel. Each panel implements
`reset_channel_state(configuration)`; it clears that state and its displayed
results without changing parameters. Generator has an intentional no-op hook
because input configuration does not control output generation.

Hardware-free tests use distinguishable synthetic multichannel blocks and fake
streams/rings. They cover routing, configuration ordering, stale data, resets,
pause preservation and device rollback without querying audio devices or
reading installed application settings. Run them with the full source suite
described in [TESTING.md](TESTING.md).
