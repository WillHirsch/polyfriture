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
configured. The current single/two-channel settings dialog remains in place
until every retained visualization supports arbitrary counts. Its adapters
use the same ordered subset contract; selecting one physical input twice
produces one row. Arbitrary subset persistence and the multiselection UI are
later roadmap work.

## A configuration boundary

Each effective selection or device change creates a strictly newer
`generation`. Re-selecting the same subset or device is a no-op. A change to
the inactive second-channel preference does not change the captured subset.
Startup without an available device has no configuration.

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
channels. As panels are generalized, each channel owns its mutable processing
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
