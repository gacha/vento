# VENTO to MQTT

## What problem does this solve?

There are these single-room air handling units with heat recovery like
VENTO Expert A50-1, A30-1 and others from [Blauberg](https://blaubergventilatoren.de).

These units are controlled by a mobile app, where the communication with the device
is done via [UDP transport protocol](https://blaubergventilatoren.de/uploads/download/ventoexpertduowsmarthousev11en.pdf).

This is a Python service, which allows to control the unit via [MQTT](https://en.wikipedia.org/wiki/MQTT) protocol.

## How to use it

Install the only dependency [paho-mqtt](https://pypi.org/project/paho-mqtt) >=2.0 and then run:

    python ./vento.py --vento-host <unit-hostname> --mqtt-host <mqtt-server-hostname>

## History

This is a fork of https://github.com/mhbosch/vent_to_mqtt

Changes made:

 - translated from German
 - added logging
 - added ability to pass commandline arguments
 - minor code improvements
