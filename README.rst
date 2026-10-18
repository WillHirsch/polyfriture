===============
friture-monitor
===============

.. image:: https://github.com/WillHirsch/friture-monitor/actions/workflows/build.yml/badge.svg
    :target: https://github.com/WillHirsch/friture-monitor/actions

**friture-monitor** is a fork of `Friture`_, an application to visualize and
analyze live audio data in real-time. Its development roadmap focuses on
monitoring multiple channels from one audio device and is tracked in
`GitHub issues`_.

friture-monitor displays audio data in several widgets, such as a scope, a
spectrum analyzer, or a rolling 2D spectrogram.

This program can be useful to analyze and equalize the audio response of a hall, or for educational purposes, etc.

Run from source::

    uv sync
    uv run friture-monitor

See INSTALL.md for platform-specific setup. The Python package is named
``friture_monitor``; settings and logs use the separate ``friture-monitor``
application identity. Upstream settings import is a subsequent roadmap item.

Friture was created by Timothée Lecomte and contributors. The name *Friture*
is a French word for *frying*, also used for *noise* in a sound. This fork
retains the upstream copyright notices and GPLv3 license; see COPYING.txt.

See the `upstream project homepage`_ for screenshots and information about Friture.

.. _Friture: https://github.com/tlecomte/friture
.. _`GitHub issues`: https://github.com/WillHirsch/friture-monitor/issues
.. _`upstream project homepage`: http://friture.org
