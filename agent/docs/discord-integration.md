# Running the agent in Discord

The agent ships a Discord bridge. It runs the same orchestrator the HTTP service runs, and it connects outbound to Discord's gateway. It needs no inbound route, no public IP, and no firewall change, so it works from your laptop or a small Linode.

## Three settings, do not confuse them

- **Intent** is what the bot is allowed to see. The bridge reads your message text, so it needs the **Message Content Intent**. Set it on the Bot tab.
- **Permissions** are what the bot can do inside a server: send a message, attach a file, react. They are per server and do not apply in DMs.
- **OAuth2 scope** is how you install it. You need the `bot` scope to invite it.

## What you need

- A Discord account, and a server you can add a bot to (or you can just DM the bot).
- The agent installed and a model provider set (see the README).
- `LINODE_TOKEN` if you want it to read your real account.

## Create the bot

1. Go to https://discord.com/developers/applications and click New Application. Name it.
2. Open the Bot tab. Click Reset Token, copy the token. This is your `DISCORD_TOKEN`. Keep it secret.
3. On the Bot tab, under Privileged Gateway Intents, turn on **Message Content Intent**. Without it the bot cannot read message text.

## Invite the bot

1. Open the OAuth2 tab, then URL Generator.
2. Scopes: check **`bot`** and **`applications.commands`**. The first installs the bot, the second registers its slash commands (`/ask`, `/help`).
3. After you check `bot`, a Bot Permissions panel appears below the scopes. Set the permissions here, in the URL generator. (The separate Bot Permissions page, the one with the permissions integer, is only a calculator; it does not attach anything.) Send Messages, Read Message History, and View Channels are the minimum; the rest enable specific features:
   - **Send Messages** (required, to reply)
   - **Read Message History** (to reply to the message it answers)
   - **Send Messages in Threads** (to answer inside a thread)
   - **Embed Links** (so the docs links it cites show a preview)
   - **Attach Files** (so it can post diagram images)
   - **Add Reactions** (so it can acknowledge your message)
   - **View Channels** (to see channels it is used in)
4. Copy the **Generated URL**, open it in a browser, and add the bot to your server.

The generated URL is a one-time invite link. It is not a setting and it does not go in `.env`. The only thing from Discord that goes in `.env` is the bot token, `DISCORD_TOKEN`.

**Already added the bot with the `bot` scope only?** Slash commands need `applications.commands`. Re-open the URL Generator, check both `bot` and `applications.commands`, open the new URL, and re-add the bot to the same server. It updates in place, you lose nothing. Then set `DISCORD_GUILD_ID`, restart the bridge, and `/ask` shows up in that server right away.

For DMs you do not need any of the permissions above. Permissions are a server concept. If you only DM the bot, the Message Content Intent and the `bot` scope are enough.

## Run it

From the `agent/` directory, with your `.env` filled in:

```bash
# add this to .env (the Bot token, not the invite URL)
DISCORD_TOKEN=your-token-here

PYTHONPATH=src python -m discord_bridge
```

The log prints "Logged in as ..." and, if `LINODE_TOKEN` is set, "Reads via akamai-cloud-mcp".

## Use it

- `/ask <question>`, the slash command, with `/help` for what to ask.
- DM the bot directly, no prefix.
- `@mention` it in a channel.
- Or type `$sa <question>` in a channel.
- `$help` and `$status` are built in.

Slash commands register to the server in `DISCORD_GUILD_ID` instantly on startup. Without that set they sync globally, which can take up to an hour to appear.

## What it does in Discord

- **Acknowledges your message** with an eyes reaction as soon as it starts, so you know it heard you. Needs Add Reactions in a server.
- **Replies cleanly.** Long answers are split under Discord's 2000-character limit, and code blocks (Terraform, CLI) stay fenced across the split.
- **Previews the docs it cites.** When it returns a source URL, Discord shows a link preview. Needs Embed Links.
- **Posts diagrams as images.** When you ask it to draw your LKE cluster or network, it renders a PNG and uploads it as an attachment instead of printing a file path. Needs Attach Files, and the diagram tools need the Graphviz `dot` binary (`pip install -e .` covers the Python side, `brew install graphviz` the binary).
- **Gates account changes.** A planned change shows Approve and Decline buttons. Only the person who asked can approve, and the agent cannot approve itself.

## Why it needs no exposure

The bridge opens an outbound websocket to Discord. Discord pushes messages to it. Nothing connects in. This is different from the HTTP service (`uvicorn api:app`), which is a REST endpoint other programs call, and which you only expose when you want that. For a demo, the Discord bridge alone is enough, and it exposes nothing.
