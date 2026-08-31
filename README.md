# safera-sense

work in progress, i dont know what im doing :D 

A Home Assistant integration for Safera Sense kitchen hoods, including the Røroshetta
rebadges. Reads the environment and stove-guard sensors, and controls the light, fan,
presets and automatic modes over BLE.

current status: works. 31 entities — 14 sensors streaming about once a second, plus a
dimmable light with colour temperature, a fan with speed feedback, auto-mode switches, the
grease filter reset, and 12 numbers for the hood's own presets.

pairing is a one-time thing: press the pairing button on the hood during setup, after that it
reconnects on its own.
