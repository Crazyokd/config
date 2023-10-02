# Ripgrep
if type rg &> /dev/null; then
	  export FZF_DEFAULT_COMMAND='rg --files'
		export FZF_DEFAULT_OPTS='-m'
fi

export http_proxy=http://192.168.1.10:7890
export https_proxy=http://192.168.1.10:7890
