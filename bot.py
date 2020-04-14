import discord
import discord.utils
from discord.ext import commands
import asyncpg
import re
import itertools
import os
import ssl

commands = discord.ext.commands
#Maximum Anderdrive
helpmsg = """```HordeBot Created By Plat#3996\n
Prefix:\n
    !t[command] or !t [command], either will work.\n
Player Commands:\n
    help - shows this message\n
    ping - sends a query to the bot and prints out the response time.\n
    compete - gives player tournament player role and allows the to enroll into tournaments, do again to take away role.\n
    enroll [tournament name] - enrolls player into a tournament with the name [name]\n
    revoke [tournament name] - unenrolls a player from a tournament with the name [name]\n
Staff Commands\n
    createtournament [name] [type] - Creates a tournament with the name [name] and as the type [type]\n
        [type] - TW-SOLOS, TW-DUOS, TW-TRIOS, TW-SQUADS, SG-SOLOS, SG-DUOS\n
    close [name] - closes the tournament with the name [name], ends enrollment.\n
    choose [name] - chooses enrolled players from tournament with the name [name] on who will play, tournament must be closed to use choose.
```"""
client = commands.Bot(command_prefix = ("!t ", "!t", "!"), case_insensitive = True, help_command=None)

isProd = os.environ.get('IS_HEROKU', None)
if isProd:
    botKey = os.environ.get('BOT_KEY', None)

ctx = ssl.create_default_context(cafile='')
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

async def create_db_pool():
    client.pg_con = await asyncpg.create_pool(os.environ['DATABASE_URL'], ssl = ctx)

@client.event
async def on_ready():
    await client.change_presence(activity=discord.Game('with your feelings'))
    print("hello")

@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("That is an invalid command!")
    else:
        print(error)

@client.command()
async def help(ctx):
    await ctx.send(helpmsg)

@client.command()
async def ping(ctx):
    await ctx.send(f'Bot latency is {round(client.latency * 1000)}ms')

@client.command()
async def compete(ctx):
    author = ctx.message.author
    role = discord.utils.get(author.guild.roles, id=673807829181792257)
    if role in ctx.author.roles:
        await author.remove_roles(role)
        await ctx.send("Rank has been removed, Do !tcompete again to be readded!")
    else:
        await author.add_roles(role)
        await ctx.send("Rank has been added, You are now a tournament player!")
        user = await client.pg_con.fetch("SELECT * FROM players WHERE user_id = $1", str(author.id))

        if not user:
            await client.pg_con.execute("INSERT INTO players (user_id, tournaments_played, enroll_score) VALUES ($1, 0, 1)", str(author.id))

typedict = {"<Record type='TW-SOLOS'>":8, "<Record type='TW-DUOS'>":8, "<Record type='TW-TRIOS'>":4, "<Record type='TW-SQUADS'>":4, "<Record type='SG-SOLOS'>":8,"<Record type='SG-DUOS'>":4}

@client.command()
async def createtournament(ctx, name, type):
    author = ctx.message.author
    staff = discord.utils.get(author.guild.roles, id=699345791478792292)
    if staff in ctx.author.roles:
        s = await client.pg_con.fetchrow("SELECT status FROM tournaments WHERE name = $1", name)
        if not (s):
            if f"<Record type='{type}'>" in typedict:
                #await client.pg_con.execute("ALTER TABLE tournaments ADD COLUMN ID SERIAL PRIMARY KEY;")
                await ctx.send(f"Creating tournament {name}, as {type}")
                await client.pg_con.execute("INSERT INTO tournaments (name, type, status, players_enrolled) VALUES ($1, $2, $3, ARRAY[]::text[])", name, type, "open")
            else:
                await ctx.send("That type of tournament doesn't exsist!")
        else:
            await ctx.send("A tournament with that name already exists!")
    else:
        await ctx.send("You do not have permission to use this command!")
    
@createtournament.error
async def createtournament_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Required argument missing, be sure to specify the name and type of the tournament you would like to create!")

@client.command()
async def enroll(ctx, name):
        role = discord.utils.get(ctx.author.guild.roles, id=673807829181792257)
        if role in ctx.author.roles:
            pname = await client.pg_con.fetchrow("SELECT user_id FROM players WHERE user_id = $1", str(ctx.author.id))
            if (pname):
                tname = await client.pg_con.fetchrow("SELECT name FROM tournaments WHERE name = $1", name)
                if (tname):
                    tstatus = await client.pg_con.fetch("SELECT status FROM tournaments WHERE name = $1", name)
                    if str(tstatus) == "[<Record status='open'>]":
                        alreadyEnrolled = await client.pg_con.fetchrow("SELECT * FROM tournaments WHERE name = $1 AND $2 = ANY (players_enrolled::text[])", name, str(ctx.message.author.id))
                        if not alreadyEnrolled:
                            author = ctx.message.author
                            await client.pg_con.execute("UPDATE ONLY tournaments SET players_enrolled = array_append(players_enrolled, $1) WHERE $2 = name", str(author.id), name)
                            rawScore = str(await client.pg_con.fetchrow("SELECT enroll_score FROM players WHERE user_id = $1", str(author.id)))
                            xtemp = re.findall(r'\d+', rawScore)
                            slist = list(map(int, xtemp))
                            currScore = int(slist[0])
                            newScore = currScore + 1
                            await client.pg_con.execute("UPDATE ONLY players SET enroll_score = $1 WHERE $2 = user_id",newScore ,str(author.id))
                            await ctx.send(f"You have enrolled into {name}, wait to see if you will be chosen to play!, or do !trevoke {name} to drop out.")
                        else:
                            await ctx.send("You are already enrolled into this tournament!")
                    else:
                        await ctx.send("Sorry, but that tournament is closed!")
                else:
                    await ctx.send("Sorry, but that tournament doesn't exsist!")
            else:
                await ctx.send("Sorry you are not initzalized into our database yet, do !t compete then try enrolling again!")
        else:
            await ctx.send("You need the Tournament Player Role to enroll into tournaments, get it by doing !tcompete")

@enroll.error
async def enroll_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Required argument missing, be sure to specify the name of the tournament you would like to enroll into!")

@client.command()
async def revoke(ctx, name):
    tname = await client.pg_con.fetchrow("SELECT name FROM tournaments WHERE name = $1", name)
    if (tname):
        tstatus = await client.pg_con.fetch("SELECT status FROM tournaments WHERE name = $1", name)
        if str(tstatus) == "[<Record status='open'>]":
            alreadyEnrolled = await client.pg_con.fetchrow("SELECT * FROM tournaments WHERE name = $1 AND $2 = ANY (players_enrolled::text[])", name, str(ctx.message.author.id))
            if alreadyEnrolled:
                author = ctx.message.author
                await client.pg_con.execute("UPDATE ONLY tournaments SET players_enrolled = array_remove(players_enrolled, $1) WHERE $2 = name", str(author.id), name)
                rawScore = str(await client.pg_con.fetchrow("SELECT enroll_score FROM players WHERE user_id = $1", str(author.id)))
                xtemp = re.findall(r'\d+', rawScore)
                slist = list(map(int, xtemp))
                currScore = int(slist[0])
                newScore = currScore - 1
                await client.pg_con.execute("UPDATE ONLY players SET enroll_score = $1 WHERE $2 = user_id",newScore ,str(author.id))
                await ctx.send(f"You have dropped out of {name}!")
            else:
                await ctx.send("You are not enrolled into this tournament!")
        else:
            await ctx.send("Sorry, but that tournament has already closed!, if you still want to drop out, contact a staff member.")
    else:
        await ctx.send("Sorry, but that tournament doesn't exsist!")

@revoke.error
async def revoke_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Required argument missing, be sure to specify the name of the tournament you would like to drop out of!")

@client.command()
async def close(ctx, name):
    author = ctx.message.author
    staff = discord.utils.get(author.guild.roles, id=699345791478792292)
    if staff in ctx.author.roles:
        tname = await client.pg_con.fetchrow("SELECT name FROM tournaments WHERE name = $1", name)
        if (tname):
            tstatus = await client.pg_con.fetch("SELECT status FROM tournaments WHERE name = $1", name)
            if str(tstatus) == "[<Record status='open'>]":
                await ctx.send(f"{name} has now been closed!")
                await client.pg_con.execute("UPDATE ONLY tournaments SET status = 'closed' WHERE $1 = name", name)
            else:
                await ctx.send("That tournament is already closed!")
        else:
            await ctx.send("Sorry, but that tournament doesn't exsist!")
    else:
        await ctx.send("You do not have permission to use this command!")

@close.error
async def close_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Required argument missing, be sure to specify the name of the tournament you would like to close!")

@client.command()
async def choose(ctx, name):
    author = ctx.message.author
    staff = discord.utils.get(author.guild.roles, id=699345791478792292)
    if staff in ctx.author.roles:
        q =  await client.pg_con.fetchrow("SELECT type FROM tournaments WHERE name = $1", name)
        tType = str(q)
        x = str(await client.pg_con.fetchrow("SELECT status FROM tournaments WHERE name = $1", name))
        if(str(x) == "<Record status='closed'>"):
            t = str(await client.pg_con.fetchrow("SELECT players_enrolled FROM tournaments WHERE name = $1", name))
            temp = re.findall(r'\d+', t) # my goodness I hate python regex
            idlist = list(map(int, temp))
            enrollScores = []
            for i in range(len(idlist)):
                s = str(await client.pg_con.fetch("SELECT enroll_score FROM players WHERE user_id = $1", str(idlist[i])))
                stemp = re.findall(r'\d+', s)
                lscore = list(map(int, stemp))
                score = lscore[0] 
                enrollScores.append(score)
            a = dict(zip(idlist, enrollScores))
            b = sorted(a.items(), key=lambda x: x[1], reverse=True)
            chosenValues = list(itertools.islice(b, typedict[tType]))
            chosenids = []
            for i in range(len(chosenValues)):
                chosenids.append(chosenValues[i][0])
            
            await ctx.send(f"The players chosen for {name} are:")
            for i in range(len(chosenids)):
                await ctx.send(f'<@{chosenids[i]}>')
                await client.pg_con.execute("UPDATE ONLY players SET enroll_score = 0 WHERE $1 = user_id", str(chosenids[i]))
                await client.pg_con.execute("UPDATE ONLY tournaments SET status = 'chosen' WHERE $1 = name", name)
        else:
            if (str(x) == "<Record status='open'>"):
                await ctx.send(f"Be sure to close the tournament before choosing with !tclose {name}")
            else:
                await ctx.send(f"Players have already been chosen for {name}!")
    else:
        await ctx.send("You do not have permission to use this command!")

@choose.error
async def choose_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Required argument missing, be sure to specify the name of the tournament you would like to choose players for!")


client.loop.run_until_complete(create_db_pool())
client.run(botKey)