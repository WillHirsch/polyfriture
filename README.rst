===========
Polyfriture
===========

.. image:: https://github.com/WillHirsch/polyfriture/actions/workflows/build.yml/badge.svg
    :target: https://github.com/WillHirsch/polyfriture/actions

**Polyfriture** is a fork of `Friture`_, an application to visualize and analyze live audio data in real-time.
Its goal is to more effectively support monitoring multiple channels from one audio device.

Polyfriture displays audio data in several widgets, such as a scope, a spectrum analyzer, or a rolling 2D spectrogram.

The application settings select one input device and any nonempty set of its
checked channels. Channels appear in physical order with one-based names; scopes
trigger from the first selected channel. Each panel uses the same parameters for
all its channels, while Generator remains an output utility.

Unavailable saved devices and channels retain their preferences for a later start.
The settings dialog shows the active fallback and explains any missing selection;
an explicit device or channel choice replaces the saved preference. Device matching
uses its name and host API, so changes to device order or the system default do not
redirect a saved selection. If that identity matches multiple devices, select one
explicitly rather than relying on an ambiguous match.

Spectrogram settings offer a clockwise 90-degree rotation, with frequency increasing
rightward and newest audio at the bottom. The channel grid is transposed while
labels remain upright; the global grid column count becomes the rotated row count.

New profiles start with Level Meter, FFT Spectrum, Spectrogram and Octave Spectrum
panels. Channel grids fill bottom-to-top, then left-to-right; the global column
setting controls plots within each panel. Panels may be added, changed or closed
independently, with one parameter set per panel shared by its channels.

This program can be useful to analyze and equalize the audio response of a hall, or for educational purposes, etc.

Friture was created by Timothée Lecomte and contributors.
The name *Friture* is a French word for *frying*, also used for *noise* in a sound.

Polyfriture is distributed under GNU GPLv3; see COPYING.txt. Modified from Friture by Will Hirsch in 2026.

See the `upstream project homepage`_ for screenshots and information about Friture.

.. _Friture: https://github.com/tlecomte/friture
.. _`GitHub issues`: https://github.com/WillHirsch/polyfriture/issues
.. _`upstream project homepage`: http://friture.org
