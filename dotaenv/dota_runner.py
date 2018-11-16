import time
import subprocess
import pyautogui as gui


RIGHT_BOT_BUTTON_X = 906
RIGHT_BOT_BUTTON_Y = 809

INTERVAL = 0.01
DURATION = 0.5
PAUSE = 1


def prepare_dota_client():
    if _is_dota_launched():
        _focus_dota_window()
    else:
        _focus_steam_window()

        # Search for Dota 2 in the library
        gui.click(x=118, y=108)
        gui.typewrite('dota', interval=INTERVAL)

        # Press play
        gui.click(x=400, y=230, pause=30)
    _enable_cheats()


def start_game():
    # Start
    gui.click(x=RIGHT_BOT_BUTTON_X, y=RIGHT_BOT_BUTTON_Y, duration=DURATION, pause=PAUSE)
    # Create lobby
    gui.click(x=858, y=418, pause=PAUSE)
    # Join coaches
    gui.click(x=807, y=484, pause=PAUSE)
    # Start game
    gui.click(x=RIGHT_BOT_BUTTON_X, y=RIGHT_BOT_BUTTON_Y, pause=PAUSE)


def restart_game():
    # Slow down the time and restart the game
    gui.press('\\', pause=PAUSE)
    gui.typewrite('host_timescale 6', interval=INTERVAL)
    gui.press('enter', pause=PAUSE)
    gui.typewrite('restart', interval=INTERVAL)
    gui.press('enter', pause=PAUSE)
    gui.press('\\', pause=PAUSE)
    time.sleep(10)

    # Start the game timer right away
    gui.press('\\', pause=PAUSE)
    gui.typewrite('dota_dev forcegamestart', interval=INTERVAL)
    gui.press('enter', pause=PAUSE)
    gui.typewrite('host_timescale 10', interval=INTERVAL)
    gui.press('enter', pause=PAUSE)
    gui.press('\\', pause=PAUSE)


def close_game():
    _focus_dota_window()

    # Bring up the menu
    gui.click(x=256, y=256, pause=2*PAUSE)
    # Disconnect
    gui.click(x=RIGHT_BOT_BUTTON_X, y=RIGHT_BOT_BUTTON_Y, pause=2*PAUSE)
    # Confirm it
    gui.click(x=585, y=585, pause=4*PAUSE)
    # Exit
    gui.click(x=1022, y=256, pause=2*PAUSE)
    # Confirm it and wait for complete closure
    gui.click(x=580, y=568, pause=15)


def _run_cmd(cmd):
    ps = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
    output = ps.stdout.read()
    ps.stdout.close()
    ps.wait()
    return output.decode('utf-8')


def _is_dota_launched():
    return _run_cmd('ps -ef | grep dota').find('dota 2 beta') != -1


def _focus_dota_window():
    _run_cmd('wmctrl -a "Dota 2"')
    time.sleep(DURATION)


def _focus_steam_window():
    # wmctrl detects the Steam's window as N/A.
    windows = _run_cmd('wmctrl -l')
    for window_info in windows.splitlines():
        if window_info.find('N/A') != -1:
            window_id = window_info[:10]
            _run_cmd('wmctrl -i -a ' + window_id)
    time.sleep(DURATION)


def _enable_cheats():
    gui.press('\\', pause=PAUSE)
    gui.typewrite('sv_cheats 1', interval=INTERVAL)
    gui.press('enter', pause=PAUSE)
    gui.press('\\', pause=PAUSE)
