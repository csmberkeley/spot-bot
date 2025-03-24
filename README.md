# spot-bot

Spot Bot is the relentless accountant of the surreptitious photos you take of each other. 

- `spot`, `spotted`: Spot people by mentioning them in a message with the keyword `spot` or `spotted` and a picture of your spot. 
- `spotboard`: Show how many times each channel member has spotted someone else. 
- `caughtboard`: Show how many times each channel member has been spotted.
- `pics`: View all pics of a person by tagging them in a message with the `pics` keyword. 
- `referendum`: Reply `referendum` to a spot to start a 24-hour vote to determine if the spot will count or not. 
- `reset`: Reset the spot record in a channel. 


### Tips
- Look out for :white_check_mark:. If you don't see :white_check_mark:, your spot didn't count!
- If you didn't spot something correctly, you can edit your message within one minute of sending it to correct the error. 
- If you delete a message, the spot will no longer count! 
- Spotbot will treat each channel of the workspace separately so different teams can maintain their own spot boards. 

## Install
[Click here to install](https://spot-bot.csmentors.org/spotbot/install/). (I know this looks really janky, but this is actually more secure than the native slack flow which does not protect against CSRF attacks.)

By installing Spot Bot, you acknowledge that you have read and agree to our [terms of use and privacy policy](https://gabeclasson.com/projects/spot-bot/terms-privacy/). 

## Technical details
Developed and tested on Python 3.8.10 in Ubuntu. 
