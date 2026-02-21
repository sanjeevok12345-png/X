#########################################################################################

#
# Description   Uses twitter API to automatically grab tweet details and spam in chan for
# 		            any tweets linked to.
#
# Version       2.3 - Fix to make sure pkgIndex location is specified. Thanks to Crowstorm
#                 for finding there was an issue :)
#               2.2 - Removing way too much spam from the auto process
#               2.1 - Throttling to stop baddies being bad
#               2.0 - Redone to use (the excellent!) twitoauth package from
#                 https://github.com/horgh/twitter-tcl. The script there is great for a
#                 pretty much fully functional client. This (dumb) script here
#                 just simply spams the contents of tweets spammed in the channel.
#               1.0 - Initial release
#
# Website       https://www.m00nie.com
#
# Notes         See comments below for packages required then create your own API
#                 keys here: https://apps.twitter.com/
#
#               Once you have setup the keys above enroll with oauth by running
#                 ".oauth-request <API key> <API secret>" via DCC and follow the
#                 instructions from there to obtain a PIN.
#
# 		          Also requires .chanset #chan +twitter
#########################################################################################
namespace eval m00nie {
	namespace eval twitter {

    # Load the two package - These can be found at the url below:
    # https://github.com/horgh/twitter-tcl
    # You need all files (including the pkgIndex.tcl) to ensure these all load
    # 	twitoauth.tcl
    # 	twitlib.tcl
    #  	pkgIndex.tcl
    # These should all be placed in the directory next to this script typically in
    # the scripts/ directory of your eggdrop folder. The auto_path variable should
    # point to this directory (it tells TCL to read the pkgIndex.tcl!
    lappend auto_path "scripts"
    package require twitlib
    package require twitoauth

    # File to save oauth key. Set this to a writable location for your bot
    variable state_file "scripts/m00nie-twitter.keys"
    
    # The three variables below control throttling in seconds.
    # First is per user
    # Second is per channel
    # Third is per tweet ID
    variable user_throt 30
    variable chan_throt 10
    variable id_throt 300

    ##### Shouldnt need to change anything below here #####
    # Auto tweet reader
    bind pubm - * m00nie::twitter::autoinfo

    # commands to register oauth
    bind dcc -|- oauth-request m00nie::twitter::dcc_oauth_request
    bind dcc -|- oauth-access m00nie::twitter::dcc_oauth_access

    # Add channel flag +/-twitter.
    setudef flag twitter
    variable version "2.3"
    variable throttled

# Initial oauth request to register via DCC
proc dcc_oauth_request {handle idx argv} {
	set argv [split $argv]
	lassign $argv ::twitlib::oauth_consumer_key ::twitlib::oauth_consumer_secret
	if {[llength $argv] != 2} {
	        putlog "Usage: .oauth-request <API key> <API secret>"
	        return
	}
        if {[catch {::twitoauth::get_request_token $::twitlib::oauth_consumer_key $::twitlib::oauth_consumer_secret} data]} {
		putlog "m00nie::twitter::dcc_oauth_request Error: $data"
		return
	}
	set url [dict get $data auth_url]
	putlog "To get your authentication verifier, visit ${url} and allow the application on your Twitter account."
	putlog "Then call .oauth-access [dict get $data oauth_token] [dict get $data oauth_token_secret] <PIN from authorization URL of .oauth-request>"
}


# Handle retrieval of OAuth access token via DCC
# if success, we store $::twitlib::oauth_token and $::twitlib::oauth_token_secret
proc dcc_oauth_access {handle idx argv} {
	set args [split $argv]
        if {[llength $args] != 3} {
                putlog "Usage: .oauth-access <oauth_token> <oauth_token_secret> <PIN> (get this PIN from .oauth-request)"
                return
        }
        lassign $args oauth_token oauth_token_secret pin
				if {[catch {::twitoauth::get_access_token $::twitlib::oauth_consumer_key $::twitlib::oauth_consumer_secret $oauth_token $oauth_token_secret $pin} data]} {
                putlog "m00nie::twitter::dcc_oauth_access Error: $data"
                return
        }
				# Set tokens
        set ::twitlib::oauth_token [dict get $data oauth_token]
        set ::twitlib::oauth_token_secret [dict get $data oauth_token_secret]
        set screen_name [dict get $data screen_name]
        putlog "Successfully retrieved access token for $screen_name. oauth enrollment completed :)"
	m00nie::twitter::save_keys
}

# Auto spam tweets in chan
proc autoinfo {nick uhost hand chan text} {
	if {[channel get $chan twitter] && [regexp -nocase -- {(?:http(?:s|).{3}|)(?:www.|)(?:twitter.com\/?.*status\/)([\d-]{1,100})} $text url id]} {
		if {$id == ""} {
			return
		}
		if {[throttlecheck $nick $chan $id]} { return 0 }
		if {[catch {::twitlib::get_status_by_id $id} status]} {
			puthelp "PRIVMSG $chan :Error: $status"
			return
		}
		puthelp "PRIVMSG $chan :\002@[dict get $status user screen_name]\002: [dict get $status full_text]"
	}
}

# Throttle based on user, chan or specific tweet
proc throttlecheck {nick chan id} {
	if {[info exists m00nie::twitter::throttled($id)]} {
			putlog "m00nie::twitter::throttlecheck Tweet: $id, is throttled at the moment"
			return 1
	} elseif {[info exists m00nie::twitter::throttled($chan)]} {
			putlog "m00nie::twitter::throttlecheck Channel $chan is throttled at the moment"
			return 1
	} elseif {[info exists m00nie::twitter::throttled($nick)]} {
			putlog "m00nie::twitter::throttlecheck User $nick is throttled at the moment"
      return 1
	} else {
			set m00nie::twitter::throttled($nick) [utimer $m00nie::twitter::user_throt [list unset m00nie::twitter::throttled($nick)]]
			set m00nie::twitter::throttled($chan) [utimer $m00nie::twitter::chan_throt [list unset m00nie::twitter::throttled($chan)]]
			set m00nie::twitter::throttled($id) [utimer $m00nie::twitter::id_throt [list unset m00nie::twitter::throttled($id)]]
			return 0
	}
}

# Get saved ids/state
proc load_keys {} {
	if {[catch {open $m00nie::twitter::state_file r} fid]} {
		putlog "m00nie::twitter::load_keys no keys/file to load"
		return
	}
	set data [read -nonewline $fid]
	set states [split $data \n]
	close $fid

	set ::twitlib::oauth_token [lindex $states 0]
	set ::twitlib::oauth_token_secret [lindex $states 1]
	set ::twitlib::oauth_consumer_key [lindex $states 2]
	set ::twitlib::oauth_consumer_secret [lindex $states 3]
	putlog "m00nie::twitter::load_keys loaded Successfully"
}

# Save states to file
proc save_keys {args} {
	if {[catch {open $m00nie::twitter::state_file w} fid]} {
		putlog "m00nie::twitter::save_keys could not save keys. Check permissions and file location: $m00nie::twitter::state_file "
  }
	puts $fid $::twitlib::oauth_token
	puts $fid $::twitlib::oauth_token_secret
	puts $fid $::twitlib::oauth_consumer_key
	puts $fid $::twitlib::oauth_consumer_secret
	close $fid
	putlog "m00nie::twitter::save_keys saved keys"
}
}
}
# If we have saved keys load them
m00nie::twitter::load_keys
putlog "m00nie::twitter $m00nie::twitter::version loaded"
