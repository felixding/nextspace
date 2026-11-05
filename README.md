# NEXTSPACE

[Wayland ARM64 CI](https://github.com/felixding/nextspace/actions/workflows/wayland.yml)

NEXTSPACE is a desktop environment that brings a [NeXTSTEP](https://en.wikipedia.org/wiki/NeXTSTEP) look and feel to Linux. I try to keep the user experience as close as possible to the original NeXT OS. It is developed according to the ["OpenStep User Interface Guidelines"](http://www.gnustep.org/resources/documentation/OpenStepUserInterfaceGuidelines.pdf).

> An explanation of the NeXTSTEP / NextStep naming convention is discussed in further detail [here](Documentation/OpenStep%20Confusion.md).

![NEXTSPACE example](Documentation/NEXTSPACE_Screenshot.png)

I want to create a fast, elegant, reliable, and easy to use desktop environment with maximum attention to user experience (usability) and visual maturity. I would like it to become a platform where applications will be running with a taste of NeXT's OS. Core applications such as Login, Workspace, and Preferences are the base for future application development and examples of visual style and application integration methods.

NEXTSPACE is not just a set of applications tightly integrated to each other. It is a core OS with frameworks, mouse cursors, fonts, colors, animations, and everything I think will help users to be effective and happy.

[Brief introduction](Applications.md) to core NEXTSPACE applications contains some details and screenshots.

## Why?
1. I like the look, feel, and design principles of NeXTSTEP.
2. I believe it will become an interesting environment for developers and comfortable (fast, easy to use, feature-rich) for users.

Unlike other 'real' and 'serious' projects, I have not yet defined a target audience for NEXTSPACE. I intentionally left aside modern UI design trends (fancy animations, shadows, gray blurry lines, flat controls, acid colors, transparency). I like the accurate, clear, grayish, and "boring" UI that helps, not hinder, to get my job done.

## Not planned
* Qualifying additional platforms before the native Wayland target is ready. Current development focuses on Debian 13 ARM64; Intel/AMD and other distributions are deferred.
* GNOME, KDE, macOS rival in terms of visual effects, modern design principles, look and feel.
* Implementing a macOS-like desktop paradigm. There is another good place for this -- see [Étoilé](http://etoileos.com).

## Installing
The current native Wayland preview targets Debian 13 ARM64. Follow the
[Debian package guide](Packaging/Debian/README.md) to build and validate the
desktop. The [implementation status](docs/Wayland-Implementation-Status.md)
records the qualified software and remaining release gates.

[Lima helpers](Tests/Lima/README.txt) support local development and testing on
Apple Silicon Macs. Lima is an optional developer tool; the Debian desktop
packages run directly on Linux.

## For developers
For those who are eager to know "How it's done?" can find information on development tasks, goals, solutions, implementation details, and build instructions on the [Wiki](https://github.com/trunkmaster/nextspace/wiki).
