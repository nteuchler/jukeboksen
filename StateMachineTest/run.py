"""Interactive PC test program for the first state-machine slice."""

from __future__ import annotations

import asyncio

from state_machine import Command, CommandType, Mode, StateMachine


HELP = """Commands:
  status                         Show current state
  mode idle|bluetooth|activity   Switch mode
  next                           Force the next step
  help                           Show these commands
  quit                           Stop the state machine
"""


async def main() -> None:
    machine = StateMachine()
    runner = asyncio.create_task(machine.run())
    await asyncio.sleep(0)

    print("Jukebox state machine started.")
    print(HELP)

    while machine.running:
        try:
            raw = await asyncio.to_thread(input, "> ")
        except EOFError:
            raw = "quit"
        parts = raw.strip().lower().split()
        if not parts:
            continue

        try:
            if parts[0] == "status":
                print(machine.status())
            elif parts[0] == "mode" and len(parts) == 2:
                await machine.send(Command(CommandType.SWITCH_MODE, parts[1]))
                await machine.commands.join()
                print(machine.status())
            elif parts[0] == "next":
                await machine.send(Command(CommandType.NEXT))
                await machine.commands.join()
                print(machine.status())
            elif parts[0] == "help":
                print(HELP)
            elif parts[0] in {"quit", "exit"}:
                await machine.send(Command(CommandType.SHUTDOWN))
                await machine.commands.join()
            else:
                print("Unknown command. Type 'help'.")
        except ValueError as error:
            print(f"Error: {error}")

    await runner
    print("State machine stopped.")


if __name__ == "__main__":
    asyncio.run(main())
