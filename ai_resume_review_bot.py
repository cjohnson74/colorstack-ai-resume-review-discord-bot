import asyncio
import logging
import random
import discord
from discord.ext import commands, tasks
import os
from utils.job_input_view import JobInputView
from utils.feedback_view import FeedbackView
from utils.resume_utils import review_resume
from utils.analytics import analytics
from config import RESUME_REVIEW_CHANNEL_ID, GIFS, HIGH_SCORE_COLOR, GOOD_SCORE_COLOR, LOW_SCORE_COLOR, BAD_SCORE_COLOR

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

def get_score_color(score):
    if score >= 8:
        return HIGH_SCORE_COLOR  # Green
    elif score >= 6:
        return GOOD_SCORE_COLOR  # Light Blue
    elif score >= 4:
        return LOW_SCORE_COLOR  # Yellow
    else:
        return BAD_SCORE_COLOR  # Red

def get_gif(score):
    if score >= 8:
        return random.choice(GIFS["high_score_gifs"])
    elif score >= 6:
        return random.choice(GIFS["good_score_gifs"])
    elif score >= 4:
        return random.choice(GIFS["low_score_gifs"])
    else:
        return random.choice(GIFS["bad_score_gifs"])

class ResumeBot(commands.Bot):
    def __init__(self, command_prefix, intents):
        super().__init__(command_prefix=command_prefix, intents=intents)
        self.job_details = None
        self._already_processing_commands = False
        
        # Configure logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler()
            ]
        )
    
    async def process_commands(self, message):
        # Prevent recursive command processing
        if self._already_processing_commands:
            return
            
        self._already_processing_commands = True
        try:
            await super().process_commands(message)
        finally:
            self._already_processing_commands = False
    
    async def on_ready(self):
        logging.info(f'Logged in as {self.user.name} ({self.user.id})')
        
    async def setup_hook(self):
        # Start the heartbeat task
        self.heartbeat_task.start()
        
        # Register commands
        self.add_commands()
        
    def add_commands(self):
        @self.command(name="resumehelp", description="Shows help information about the resume review bot")
        async def help_command(ctx):
            embed = discord.Embed(
                title="Resume Review Bot Help",
                description="This bot provides AI-powered resume reviews. Here's how to use it:",
                color=0x0699ab
            )
            
            embed.add_field(
                name="📝 How to Get a Resume Review",
                value="1. Go to the resume review forum channel\n"
                      "2. Create a new post\n"
                      "3. Attach your resume as a PDF file\n"
                      "4. Wait for the bot to analyze your resume",
                inline=False
            )
            
            embed.add_field(
                name="🔍 What's Included in the Review",
                value="• Experience bullet point analysis\n"
                      "• Project bullet point analysis\n"
                      "• Resume formatting feedback\n"
                      "• Suggestions for improvement\n"
                      "• Overall score",
                inline=False
            )
            
            embed.add_field(
                name="📊 Commands",
                value="• `!resumehelp` - Shows this help message\n"
                      "• `!resumestats` - Shows usage statistics (admin only)",
                inline=False
            )
            
            embed.set_footer(text="• Powered by ColorStack UF ResumeAI •")
            await ctx.send(embed=embed)
            
        @self.command(name="resumestats", description="Shows usage statistics (admin only)")
        @commands.has_permissions(administrator=True)
        async def stats_command(ctx):
            # Get usage report from analytics
            report = analytics.get_usage_report()
            
            embed = discord.Embed(
                title="Resume Review Bot Statistics",
                description="Usage statistics for the Resume Review Bot",
                color=0x0699ab
            )
            
            embed.add_field(
                name="📊 Resume Reviews",
                value=f"Total reviews: {report['total_reviews']}",
                inline=False
            )
            
            # Add average scores
            scores = report['average_scores']
            embed.add_field(
                name="⭐ Average Scores",
                value=f"Overall: {scores['overall']}/10\n"
                      f"Experiences: {scores['experiences']}/10\n"
                      f"Projects: {scores['projects']}/10\n"
                      f"Formatting: {scores['formatting']}/10",
                inline=False
            )
            
            # Add API usage
            api_usage = report['api_usage']
            embed.add_field(
                name="🤖 API Usage",
                value=f"Total requests: {api_usage['total_requests']}\n"
                      f"Total tokens: {api_usage['total_tokens']}\n"
                      f"Estimated cost: ${api_usage['estimated_cost']}",
                inline=False
            )
            
            # Add feedback ratings
            feedback = report['feedback']
            embed.add_field(
                name="📝 User Feedback",
                value=f"Total ratings: {feedback['total_ratings']}\n"
                      f"Average rating: {feedback['average_rating']}/5",
                inline=False
            )
            
            embed.set_footer(text="• Powered by ColorStack UF ResumeAI •")
            await ctx.send(embed=embed)
            
        # Error handler for the stats command
        @stats_command.error
        async def stats_command_error(ctx, error):
            if isinstance(error, commands.MissingPermissions):
                await ctx.send("You don't have permission to use this command.")
            else:
                logging.error(f"Error in stats command: {error}")
                await ctx.send("An error occurred while processing this command.")
    
    @tasks.loop(minutes=20)
    async def heartbeat_task(self):
        logging.info("Heartbeat: Bot is still running")
    
    async def on_message(self, message):
        # Don't respond to our own messages
        if message.author == self.user:
            return
            
        # Process commands first (our override will prevent double processing)
        await self.process_commands(message)
        
        # Debug logging for channel IDs
        logging.info(f"Message channel type: {type(message.channel).__name__}")
        logging.info(f"Message channel ID: {message.channel.id}")
        if hasattr(message.channel, 'parent_id'):
            logging.info(f"Parent channel ID: {message.channel.parent_id}")
        else:
            logging.info("Channel has no parent_id attribute")
        logging.info(f"Expected forum channel ID: {RESUME_REVIEW_CHANNEL_ID}")
        
        # Check if this is a command (skip if it is)
        if message.content.startswith(self.command_prefix):
            return
            
        # Check if this is the resume review channel
        is_valid_channel = (
            message.channel.id == RESUME_REVIEW_CHANNEL_ID or
            (hasattr(message.channel, 'parent_id') and message.channel.parent_id == RESUME_REVIEW_CHANNEL_ID)
        )
        
        if not is_valid_channel:
            logging.info(f"Message is not in the specified resume review channel")
            return
            
        logging.info(f"Message received in resume review channel: {message.content}")

        if message.attachments:
            for attachment in message.attachments:
                if attachment.filename.lower().endswith('.pdf'):
                    logging.info(f"Processing attachment: {attachment.filename}")
                    
                    # Sending the initial feedback embed
                    main_embed = discord.Embed(
                        title="Do you have job posting to review for?",
                        color=0x0699ab
                    )
                    view = JobInputView(self, message)
                    message_with_view = await message.channel.send(embed=main_embed, view=view)
                    
                    await view.wait()
                    
                    if view.job_details:
                        self.job_details = view.job_details
                    else:
                        await message.channel.send("No job details provided. Providing general resume formatting feedback.")
                        self.job_details = None
                    
                    await message_with_view.delete()
                    
                    # Use a specific processing GIF for the loading state
                    processing_gif_url = "https://i.giphy.com/media/v1.Y2lkPTc5MGI3NjExcnlrNXdsdWRnbTA2ZTNjbHIxOG1jOGc4ZndpM3o2aWY2YW04d2cwdiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/paKhPtCfM7RDQyRyGf/giphy.gif"
                    loading_embed = discord.Embed(
                        title="This could take a minute or two -- our reviewer is hard at work! 😜",
                        color=0x0699ab
                    )
                    loading_embed.set_image(url=processing_gif_url)
                    loading_embed.add_field(name="\u200b", value="• Inspired by [Oyster](https://github.com/colorstackorg/oyster) 🦪 •", inline=False)
                    loading_embed.set_footer(text="• Powered by ColorStack UF ResumeAI •")
                    loading_message = await message.channel.send(embed=loading_embed)

                    main_embed = discord.Embed(
                        title="AI Resume Feedback",
                        description="Currently, the resume review tool will only give feedback on your bullet points for experiences and projects, as well as, resume formatting. This does not serve as a complete resume review, so you should still seek feedback from peers. Additionally, this tool relies on AI and may not always provide the best feedback, so take it with a grain of salt.\n\n**Disclaimer:** Any suggestions provided are purely examples and should not be added as-is without verification of accuracy.\n\n**Note:** We are comparing your resume to Jake's resume for formatting feedback. You can view Jake's resume [here](https://www.overleaf.com/latex/templates/jakes-resume/syzfjbzwjncs).",
                        color=0x0699ab
                    )
                    await message.channel.send(embed=main_embed)
                    user_resume_bytes = await attachment.read()
                    jake_resume_bytes = open("resumes/jakes-resume.pdf", "rb").read()

                    try:
                        if self.job_details:
                            feedback = review_resume(resume_user=user_resume_bytes, resume_jake=jake_resume_bytes, job_title=self.job_details["job_title"], company=self.job_details["company"], min_qual=self.job_details["min_qual"], pref_qual=self.job_details["pref_qual"])
                        else:
                            feedback = review_resume(resume_user=user_resume_bytes, resume_jake=jake_resume_bytes)

                        # Log the feedback structure
                        logging.info(f"Feedback structure: {feedback}")

                        # Check if feedback is a dictionary
                        if not isinstance(feedback, dict):
                            logging.error("Feedback is not a dictionary.")
                            return

                        # Access experiences safely
                        experiences = feedback.get("experiences", [])
                        if not isinstance(experiences, list):
                            logging.error("Expected 'experiences' to be a list.")
                            return

                        logging.info(f"Experiences: {experiences}")  # Log the experiences

                        total_experiences_score = 0
                        total_projects_score = 0
                        total_formatting_score = 0
                        total_experiences_bullets = 0
                        total_projects_bullets = 0

                        for experience in experiences:
                            if isinstance(experience, dict):
                                experience_embed = discord.Embed(title=f"**Experience at {experience.get('company', 'Unknown')} - {experience.get('role', 'Unknown')}**\n", color=0xe5e7eb)
                                await message.channel.send(embed=experience_embed)
                                bullets = experience.get('bullets', [])
                                if not isinstance(bullets, list):
                                    logging.error("Expected 'bullets' to be a list.")
                                    continue

                                for idx, bullet in enumerate(bullets):
                                    if isinstance(bullet, dict):
                                        total_experiences_score += bullet.get('score', 0)
                                        total_experiences_bullets += 1
                                        rewrites = "\n\n> ".join(bullet.get('rewrites', [])) if bullet.get('rewrites') else None
                                        bullet_embed = discord.Embed(title=f"{bullet.get('score', 0)}/10.0", color=get_score_color(bullet.get('score', 0)))
                                        bullet_embed.add_field(name="", value=f"> *{bullet.get('content', 'No content')}*\n", inline=False)
                                        bullet_embed.add_field(name="Feedback", value=f"> {bullet.get('feedback', 'No feedback')}\n", inline=False)
                                        if rewrites:
                                            bullet_embed.add_field(name="Suggestions ", value=f"> {rewrites}", inline=False)
                                        await message.channel.send(embed=bullet_embed)
                                    else:
                                        logging.error("Bullet item is not a dictionary.")
                            else:
                                logging.error("Experience item is not a dictionary.")

                        avg_expereinces_final_score = 0 if total_experiences_bullets == 0 else total_experiences_score / total_experiences_bullets
                        expereinces_final_embed = discord.Embed(
                            title="Experience Section Score",
                            color=get_score_color(avg_expereinces_final_score)
                        )
                        expereinces_final_embed.add_field(name=f"{round(avg_expereinces_final_score, 1)}/10.0", value="", inline=False)
                        await message.channel.send(embed=expereinces_final_embed)

                        # Access projects safely
                        projects = feedback.get("projects", [])
                        if not isinstance(projects, list):
                            logging.error("Expected 'projects' to be a list.")
                            return

                        for project in projects:
                            if isinstance(project, dict):
                                # Check if the project has a 'title' field, otherwise try 'name'
                                project_title = project.get('title', project.get('name', 'Unknown'))
                                project_embed = discord.Embed(title=f"**Project: {project_title}**\n", color=0xe5e7eb)
                                await message.channel.send(embed=project_embed)
                                bullets = project.get('bullets', [])
                                if not isinstance(bullets, list):
                                    logging.error("Expected 'bullets' to be a list.")
                                    continue

                                for idx, bullet in enumerate(bullets):
                                    if isinstance(bullet, dict):
                                        total_projects_score += bullet.get('score', 0)
                                        total_projects_bullets += 1
                                        rewrites = "\n\n> ".join(bullet.get('rewrites', [])) if bullet.get('rewrites') else None
                                        bullet_embed = discord.Embed(title=f"{bullet.get('score', 0)}/10.0", color=get_score_color(bullet.get('score', 0)))
                                        bullet_embed.add_field(name="", value=f"> *{bullet.get('content', 'No content')}*\n", inline=False)
                                        bullet_embed.add_field(name="Feedback", value=f"> {bullet.get('feedback', 'No feedback')}\n", inline=False)
                                        if rewrites:
                                            bullet_embed.add_field(name="Suggestions ", value=f"> {rewrites}", inline=False)
                                        await message.channel.send(embed=bullet_embed)
                                    else:
                                        logging.error("Bullet item is not a dictionary.")
                            else:
                                logging.error("Project item is not a dictionary.")

                        avg_projects_final_score = 0 if total_projects_bullets == 0 else total_projects_score / total_projects_bullets
                        projects_final_embed = discord.Embed(
                            title="Projects Section Score",
                            color=get_score_color(avg_projects_final_score)
                        )
                        projects_final_embed.add_field(name=f"{round(avg_projects_final_score, 1)}/10.0", value="", inline=False)
                        await message.channel.send(embed=projects_final_embed)

                        # Access formatting safely
                        formatting = feedback.get("formatting", {})
                        if not isinstance(formatting, dict):
                            logging.error("Expected 'formatting' to be a dictionary.")
                            return

                        formatting_embed = discord.Embed(title="**Formatting Feedback**\n", color=0xe5e7eb)
                        await message.channel.send(embed=formatting_embed)

                        # Group formatting aspects
                        font_aspects = ['font_consistency', 'font_choice', 'font_size']
                        layout_aspects = ['alignment', 'margins', 'overall_layout', 'page_utilization', 'is_single_page']
                        spacing_aspects = ['line_spacing', 'section_spacing', 'bullet_points']
                        other_aspects = ['headings', 'contact_information', 'consistency']

                        # Process font aspects
                        font_score = 0
                        font_feedback = []
                        for aspect in font_aspects:
                            if aspect in formatting:
                                data = formatting[aspect]
                                font_score += data.get('score', 0)
                                if data.get('feedback'):
                                    font_feedback.append(f"• {data['feedback']}")
                        
                        if font_feedback:
                            font_embed = discord.Embed(
                                title=f"Font & Typography: {round(font_score/len(font_aspects), 1)}/10.0",
                                color=get_score_color(font_score/len(font_aspects))
                            )
                            font_embed.add_field(name="Feedback", value="\n".join(font_feedback), inline=False)
                            await message.channel.send(embed=font_embed)

                        # Process layout aspects
                        layout_score = 0
                        layout_feedback = []
                        for aspect in layout_aspects:
                            if aspect in formatting:
                                data = formatting[aspect]
                                layout_score += data.get('score', 0)
                                if data.get('feedback'):
                                    layout_feedback.append(f"• {data['feedback']}")
                        
                        if layout_feedback:
                            layout_embed = discord.Embed(
                                title=f"Layout & Structure: {round(layout_score/len(layout_aspects), 1)}/10.0",
                                color=get_score_color(layout_score/len(layout_aspects))
                            )
                            layout_embed.add_field(name="Feedback", value="\n".join(layout_feedback), inline=False)
                            await message.channel.send(embed=layout_embed)

                        # Process spacing aspects
                        spacing_score = 0
                        spacing_feedback = []
                        for aspect in spacing_aspects:
                            if aspect in formatting:
                                data = formatting[aspect]
                                spacing_score += data.get('score', 0)
                                if data.get('feedback'):
                                    spacing_feedback.append(f"• {data['feedback']}")
                        
                        if spacing_feedback:
                            spacing_embed = discord.Embed(
                                title=f"Spacing & Organization: {round(spacing_score/len(spacing_aspects), 1)}/10.0",
                                color=get_score_color(spacing_score/len(spacing_aspects))
                            )
                            spacing_embed.add_field(name="Feedback", value="\n".join(spacing_feedback), inline=False)
                            await message.channel.send(embed=spacing_embed)

                        # Process other aspects
                        other_score = 0
                        other_feedback = []
                        for aspect in other_aspects:
                            if aspect in formatting:
                                data = formatting[aspect]
                                other_score += data.get('score', 0)
                                if data.get('feedback'):
                                    other_feedback.append(f"• {data['feedback']}")
                        
                        if other_feedback:
                            other_embed = discord.Embed(
                                title=f"Other Formatting: {round(other_score/len(other_aspects), 1)}/10.0",
                                color=get_score_color(other_score/len(other_aspects))
                            )
                            other_embed.add_field(name="Feedback", value="\n".join(other_feedback), inline=False)
                            await message.channel.send(embed=other_embed)

                        # Show overall formatting score
                        overall_score = formatting.get('overall_score', 0)
                        overall_embed = discord.Embed(
                            title=f"Overall Formatting Score: {round(overall_score, 1)}/10.0",
                            color=get_score_color(overall_score)
                        )
                        await message.channel.send(embed=overall_embed)

                        final_score = (avg_projects_final_score + avg_expereinces_final_score + total_formatting_score) / 3.0  # Ensure float division
                        gif_url = get_gif(final_score)
                        # Completion message
                        final_embed = discord.Embed(
                            title="AI Resume Review Complete! 🎉",
                            color=get_score_color(final_score)
                        )
                        final_embed.set_image(url=gif_url)
                        final_embed.add_field(name="\u200b", value="• Inspired by [Oyster](https://github.com/colorstackorg/oyster) 🦪 •", inline=False)
                        final_embed.set_footer(text="• Powered by ColorStack UF ResumeAI •")
                        await loading_message.edit(embed=final_embed)
                        
                        # For the final score embed, use a GIF based on the score
                        score_based_gif_url = get_gif(final_score)
                        final_score_embed = discord.Embed(title=f"Final Score: {round(final_score, 1)}/10.0", color=get_score_color(final_score))
                        final_score_embed.set_image(url=score_based_gif_url)
                        final_score_embed.add_field(name="\u200b", value="• Inspired by [Oyster](https://github.com/colorstackorg/oyster) 🦪 •", inline=False)
                        final_score_embed.set_footer(text="• Powered by ColorStack UF ResumeAI •")
                        await message.channel.send(embed=final_score_embed)
                        
                        # Track the resume review in analytics
                        scores = {
                            "overall": final_score,
                            "experiences": avg_expereinces_final_score,
                            "projects": avg_projects_final_score,
                            "formatting": total_formatting_score
                        }
                        analytics.track_resume_review(message.author.id, message.guild.id, scores)
                        
                        # Ask for feedback
                        feedback_embed = discord.Embed(
                            title="How was your experience?",
                            description="Please rate this resume review to help us improve!",
                            color=0x0699ab
                        )
                        feedback_view = FeedbackView(message.author.id, message.guild.id)
                        await message.channel.send(embed=feedback_embed, view=feedback_view)
                        
                    except Exception as e:
                        logging.error(f"Failed to process PDF attachment: {e}")
                        await message.channel.send(f"Sorry, I encountered an error while processing your resume. Error details: {str(e)}")
                        # Log the full traceback for debugging
                        import traceback
                        logging.error(f"Full error traceback: {traceback.format_exc()}")

def start_bot(token):
    # Discord Bot Setup
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    bot = ResumeBot(command_prefix="!", intents=intents)
    
    
    bot.run(token)