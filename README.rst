===========
Polyfriture
===========

.. image:: https://github.com/WillHirsch/polyfriture/actions/workflows/build.yml/badge.svg
    :target: https://github.com/WillHirsch/polyfriture/actions

**Polyfriture** is a fork of `Friture`_, an application to visualize and
analyze live audio data in real-time. Its development roadmap focuses on
monitoring multiple channels from one audio device and is tracked in
`GitHub issues`_.

Polyfriture displays audio data in several widgets, such as a scope, a
spectrum analyzer, or a rolling 2D spectrogram.

This program can be useful to analyze and equalize the audio response of a hall, or for educational purposes, etc.

Run from source::

    uv sync
    uv run polyfriture

See INSTALL.md for platform-specific setup. The Python package is named
``polyfriture``; settings and logs use the separate ``polyfriture``
application identity. Upstream settings import is a subsequent roadmap item.

Friture was created by Timothée Lecomte and contributors. The name *Friture*
is a French word for *frying*, also used for *noise* in a sound.

License and fork modifications
------------------------------

Polyfriture is distributed under the GNU General Public License, version 3
(GPLv3); see COPYING.txt for the full license. Existing upstream and third-party
copyright, license, and warranty notices are retained.

Copyright (C) 2026 Will Hirsch for the Polyfriture modifications.

On 18 October 2026, Will Hirsch modified Friture to establish Polyfriture's
application identity, Python package, settings and log namespaces, packaging,
and documentation.

See the `upstream project homepage`_ for screenshots and information about Friture.

.. _Friture: https://github.com/tlecomte/friture
.. _`GitHub issues`: https://github.com/WillHirsch/polyfriture/issues
.. _`upstream project homepage`: http://friture.org
