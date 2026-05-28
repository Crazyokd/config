# append and unique history
history -a && cp $HOME/.bash_history logout.txt && tac logout.txt | awk '!a[$0]++' | tac > $HOME/.bash_history && rm logout.txt
