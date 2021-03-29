# bot.py
import os
import discord
import random
from dotenv import load_dotenv
load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.all()
intents.members = True
client = discord.Client(intents=intents)

@client.event
async def on_ready():
	print('Bot ready!')
	print('Connected to:\n')
	for guild in client.guilds: 
		print (f'   {guild}')

@client.event
async def on_message(message):
	
	#hello there
	ignoreSymbols = '!,.?*| '
	response = 'General Kenobi!'

	text = message.content.lower()
	for symbol in text:
		if symbol in ignoreSymbols:
			text = text.replace(symbol, '')

	if (text == "hellothere"):
		await message.channel.send(response)
		print (f'In {message.guild} #{message.channel}:\n   {message.author} ᴬᴷᴬ {message.author.display_name} >>> {message.content}\n   {client.user} ᴬᴷᴬ {client.user.display_name} >>> {response}\n\n')

	#pfp
	if message.content.startswith('pfp'):

		requestedRawString = message.content[4:]

		requestedID = discord.utils.get(client.get_all_members(), display_name = requestedRawString).id

		requestedUser = client.get_user(requestedID)

		await message.channel.send(f'{requestedUser.name} has the following profile picture:')
		await message.channel.send(requestedUser.avatar_url)
		print (f'{message.author} requested the pfp of {requestedRawString}\n\n')

	#echo
	if message.content.startswith('echo') and message.author.id == 595719716560175149:
		messageParts = message.content.split('\n', maxsplit = 3)
		sendChannel = discord.utils.get(client.get_all_channels(), guild__name = messageParts[1], name = messageParts[2])
		await sendChannel.send(messageParts[3])
		print (f'Sent "{messageParts[3]}" to channel #{sendChannel} in {sendChannel.guild}\n')

	#@someone
	if '@someone' in message.content:
		randomMember = random.choice(message.guild.members)
		print (f'{message.author.name} randomly pinged @{randomMember.display_name}')
		await message.channel.send(f'<@!{randomMember.id}>')

	#stalin
	if message.content.startswith('stalin'):
		rawList = message.content[7:]
		rawList = rawList.replace(' ', '')

		unsortedStringList = rawList.split(',')

		unsortedList = []
		for i in unsortedStringList:
			unsortedList.append(int(i))

		sortedList = []
		for n in range(len(unsortedList)):
			if n == 0:
				sortedList.append(unsortedList[n])

			elif unsortedList[n] >= sortedList[-1]:
				sortedList.append(unsortedList[n])

		print (f'{message.author} sorted {unsortedList} into {sortedList}')

		formattedList = ''
		for n in range(len(sortedList)):
			if n == 0: 
				formattedList += str(sortedList[n])
			else:
				formattedList += f', {str(sortedList[n])}'
		await message.channel.send(formattedList)



client.run(TOKEN)