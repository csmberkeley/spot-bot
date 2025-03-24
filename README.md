# spot-bot

Spot Bot is the relentless accountant of the surreptitious photos you take of each other. 

- `spot`, `spotted`: Spot people by mentioning them in a message with the keyword `spot` or `spotted` and a picture of your spot. 
- `spotboard`: Show how many times each channel member has spotted someone else. `spotboard 20` will show the top 20 spotters. 
- `caughtboard`: Show how many times each channel member has been spotted. `caughtboard 20` will show the top 20 who've been caught.
- `pics`: View all pics of a person by tagging them in a message with the `pics` keyword. 
- `referendum`: Reply `referendum` to a spot to start a 24-hour vote to determine if the spot will count or not. 
- `reset`: Reset the spot record in a channel. 


### Tips
- Look out for :white_check_mark:. If you don't see :white_check_mark:, your spot didn't count!
- If you didn't spot something correctly, you can edit your message within one minute of sending it to correct the error. 
- If you delete a message, the spot will no longer count! 
- Spotbot will treat each channel of the workspace separately so different teams can maintain their own spot boards. 

## Install
[Click here to install](https://spot-bot.onrender.com/spotbot/install/). (I know this looks really janky, but this is actually more secure than the native slack flow which does not protect against CSRF attacks.)

By installing Spot Bot, you acknowledge that you have read and agree to our [terms of use and privacy policy](https://gabeclasson.com/projects/spot-bot/terms-privacy/). 

## Technical details
Developed and tested on Python 3.8.10 in Ubuntu. WSL was used to develop in Linux on a Windows PC. 

You will need to set up a virtual environment to test locally and then install the requirements in `requirements.txt`. 

You will also need a `.env` file with the following keys: `SPOTBOT_CLIENT_ID`, `SPOTBOT_CLIENT_SECRET`, `SPOTBOT_SECURE_LINK`, `SPOTBOT_SIGNING_SECRET`. `SPOTBOT_SECURE_LINK` refers to a link for the Mongo endpoint, i.e. mongodb+srv://...

Once the virtual environment is set up, the following command will start it. 

    source venv/bin/activate

In order to develop locally, you will need to have a Slack App configured, and also have a way for your local server to be accessed by Slack. We used ngrok during development. If you use ngrok, be sure that the port you're using matches up with the port that the server is being hosted on. More information can be found here: https://tools.slack.dev/node-slack-sdk/tutorials/local-development/. This is particularly annoying because you will have to input your bespoke ngrok public URL into the configuration settings for your Slack app each time. 

You will also need to configure the MongoDB database to accept traffic from your IP address, or else you will not be able to access the database.

Once all that is configured, you can start the local server with 

    bash run.sh
