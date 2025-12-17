import subprocess
from watchfiles import watch

def start_bot():
    return subprocess.Popen([
        "python",
        "-u",
        "-m",
        "telegram.run_bot",
    ])

if __name__ == "__main__":
    print("")
#    process = start_bot()

#    for changes in watch("."):
#        print("Changes detected, restarting bot…")
#        process.kill()
#        process = start_bot()