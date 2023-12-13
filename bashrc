# Ripgrep
if type rg &> /dev/null; then
	  export FZF_DEFAULT_COMMAND='rg --files'
		export FZF_DEFAULT_OPTS='-m'
fi

# net proxy
export http_proxy=http://192.168.1.10:7890
export https_proxy=http://192.168.1.10:7890

## history related
# Avoid duplicates
export HISTCONTROL=ignoredups:erasedups
# When the shell exits, append to the history file instead of overwriting it
shopt -s histappend
# After each command, append to the history file and reread it
#export PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND$'\n'}history -a; history -c; history -r"

# set up a bat -> batcat symlink
mkdir -p ~/.local/bin
ln -s /usr/bin/batcat ~/.local/bin/bat >/dev/null 2>&1
