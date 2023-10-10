# append and unique history
history -a && cp $HOME/.bash_history logout.txt && awk '!a[$0]++' $HOME/logo    ut.txt > $HOME/.bash_history && rm logout.txt
