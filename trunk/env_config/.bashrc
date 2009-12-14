#!/bin/sh

export EDITOR="emacs"

alias hh="ssh jshiehco@jesseshieh.com"
alias e="ls -G"
alias ee="ls -Gl"
alias ea="ls -Ga"
alias c="cd"
alias o="cd .."
alias u="$EDITOR"
alias mysql="/usr/local/mysql/bin/mysql"
alias j="ssh jesses.bej"
alias n="ssh noojenco@box403.bluehost.com"
alias t="ssh jesse@edwardsshieh.com"
alias q="exit"

alias y="svn update"
alias p="svn status"
alias up="appcfg.py update /Users/jesses/AppEngine/secretsanta-jshieh"
alias s="svn commit"
alias sup="s && up"
alias dev="c ~/Documents/workspace/edwardsshieh-main/mysite/"
alias rmdes="c ~/Dropbox/Racemonger/Design"
alias vps="ssh jesse@66.249.20.237"
alias ..=". ~/.bashrc"
alias captpl="u /Workspace/edwardsshieh-main/mysite/real_estate_investment_analysis/templates/caprate.html"
alias views="u /Workspace/edwardsshieh-main/mysite/real_estate_investment_analysis/views.py"
alias tests="u /Workspace/edwardsshieh-main/mysite/real_estate_investment_analysis/tests.py"
alias dj="cd /Library/Frameworks/Python.framework/Versions/2.4/lib/python2.4/site-packages/django"
alias js="cd /Workspace/edwardsshieh-main/mysite/media/js"
alias css="cd /Workspace/edwardsshieh-main/mysite/media/css"
alias tpl="cd /Workspace/edwardsshieh-main/mysite/real_estate_investment_analysis/templates/"

alias start_mysql="sudo /usr/local/mysql/bin/mysqld_safe"
alias start_squid="sudo /usr/local/squid/sbin/squid -NCd1"

function bak() {
  cp $1 $1.bak
}
