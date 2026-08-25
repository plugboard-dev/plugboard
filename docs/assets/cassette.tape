Output demo.gif
Set FontSize 30
Set Margin 20
Set MarginFill "#075D7A"
Set BorderRadius 10

Set Theme { "background": "#1C0F13", "foreground": "#CC9C4A", "black": "#1C0F13", "red": "#D65780", "green": "#49726A", "yellow": "#CC9C4A", "blue": "#075D7A", "magenta": "#D65780", "cyan": "#8A875A", "white": "#F9F9F9", "brightBlack": "#C2C2C2", "brightRed": "#D65780", "brightGreen": "#49726A", "brightYellow": "#CC9C4A", "brightBlue": "#075D7A", "brightMagenta": "#D65780", "brightCyan": "#8A875A", "brightWhite": "#F9F9F9", "cursor": "#CC9C4A" }

Sleep 1s
Type "plugboard ai init"
Enter
Sleep 1.5s
Type "Start your AI agent and build a model..."
Sleep 1s
Backspace@2ms 40
Sleep 0.5
Type "copilot -p "
Type '"I want to simulate a production line with three machines in series. Each machine has a processing time drawn from a normal distribution and a 5% chance of failure. Model the throughput over 1000 time steps and save the results to a CSV. Create a plugboard model for this simulation and export it to YAML."'
Sleep 4s
Backspace@2ms 317
Sleep 0.5s
Type "plugboard process run production_line.yaml"
Enter
Sleep 6s