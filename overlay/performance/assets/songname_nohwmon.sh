
#!/bin/bash

exec 3> >(wayvrctl batch)
echo "panel-modify watch listenforsong set-visible 0" >&3
last_name=""
while true; do
    name="$(playerctl metadata title 2>/dev/null)"
    name="${name:0:20}"
    
    if [ "$name" != "$last_name" ]; then
        echo "panel-modify watch songname set-text \"$name\"" >&3
        last_name="$name"
    fi
    
    sleep 5
done