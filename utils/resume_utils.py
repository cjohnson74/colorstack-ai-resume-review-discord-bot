import json
import logging
import os
import tiktoken
from pydantic import ValidationError
from models import ResumeFeedback
from utils.anthropic_utils import get_chat_completion
from utils.pdf_utils import analyze_font_consistency, check_single_page, convert_pdf_to_image, extract_text_and_formatting

# Configure logging for Heroku
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Only use StreamHandler for Heroku
    ]
)

# Create a logger specific to this module
logger = logging.getLogger(__name__)
logger.info("Resume utils module initialized")

def review_resume(resume_user: bytes, resume_jake: bytes, job_title: str = None, company: str = None, min_qual: str = None, pref_qual: str = None) -> dict:
    logger.info("Starting resume review process")
    logger.info(f"Job title: {job_title}, Company: {company}")
    
    job_details = {
        "job_title": "Software Engineer" if job_title is None else job_title,
        "company": "Google" if company is None else company,
        "min_qual": "Education: Currently pursuing a Bachelor's or Master's degree in Computer Science, a related technical field, or equivalent practical experience.\nProgramming Skills: Proficiency in at least one programming language (e.g., Python, Java, C++, Go).\nComputer Science Fundamentals: Solid understanding of data structures, algorithms, and complexity analysis.\nTechnical Experience: Experience with software development, demonstrated through personal projects, coursework, or internships.\nProblem-Solving Ability: Strong analytical and problem-solving skills, with the ability to apply theoretical concepts to practical scenarios.\nCollaboration and Communication: Ability to work effectively in a team environment, with strong written and verbal communication skills." if min_qual is None else min_qual,
        "pref_qual": "Advanced Coursework: Completed coursework or have practical experience in advanced computer science topics such as distributed systems, machine learning, or security.\nTechnical Experience: Internships or co-op experience in a software development role, or significant contributions to open-source projects.\nCoding Competitions: Participation in coding competitions or technical challenges, such as competitive programming or hackathons.\nProject Experience: Demonstrated experience with complex software projects, either through internships, personal projects, or academic coursework.\nSoft Skills: Proven ability to take initiative, manage multiple tasks effectively, and adapt to new challenges in a fast-paced environment.\nLeadership and Impact: Experience in leadership roles, or demonstrated impact through technical or non-technical contributions." if pref_qual is None else pref_qual
    }

    extracted_data_jake_resume = extract_text_and_formatting(resume_jake)

    logger.debug(f"Extracted data: {extracted_data_jake_resume}")

    if not isinstance(extracted_data_jake_resume, dict):
        logger.error("Extracted Jake resume data is not a dictionary.")
        raise ValueError("Extracted Jake resume data must be a dictionary.")

    formatting_info_jake_resume = extracted_data_jake_resume["formatting"]

    # Example of processing formatting_info
    for index, item in enumerate(formatting_info_jake_resume):
        # Ensure item is a dictionary
        if isinstance(item, dict):
            text = item.get("text")
            font = item.get("font")
            size = item.get("size")
            bbox = item.get("bbox")
            
            # Log the extracted formatting information
            logger.info(f"Formatting info [{index}]: text='{text}', font='{font}', size={size}, bbox={bbox}")
        else:
            logger.error(f"Formatting info item at index {index} is not a dictionary: {item}")

    # Add information from the PDFs
    dos_and_donts = """
    Do:
    - Make it one page
    - Create a master resume listing everything
    - Keep it simple and easy to read
    - Utilize a Resume Template
    - Use a different version for each type of role
    - Create bullet points answering What, How, Why?
    - Brag about yourself and what you've done
    - Save and Send as a PDF with your name (ex. "Last Name First Name" Resume 2022)

    Don't:
    - Lie about experience
    - Get in the weeds with your bullet points
    - Add an objective statement
    - Get too creative with fonts/colors
    - Include pictures
    - Downplay your accomplishments
    - Use long bullet points or too many words
    - Re-edit too much
    """

    bullet_point_guidelines = """
    Bullet points should follow the Question Model: What, How, Why?
    - What: Explains what you did, what you built, what you contributed
    - How: Explains how you built it, what skills you developed
    - Why: Explains why it mattered, what impact you had on the company

    Example #1: Company Internship
    Developed a website extension (what) using HTML, Node JS, and CSS (how)   resulting in an increase  in website traffic of 20% (why)

    Example #2: Research or On-Campus experience
    Created a database (what) using Python, React, and C# (how)  in order to help the college make strategic decisions for 10K students(why)   

    Example #3: TA or Tutor experience
    Assisted 150 students in a CS course(what) in learning C++ (how) resulting in an average class  average of a B+(why)

    Action Verbs to use:
    Leadership: Modified, Standardized, Converted, Replaced, Redesigned, Strengthened, Customized, Restructured, Refined, Updated, Influenced, Revamped
    Management: Oversaw, Executed, Produced, Coordinated, Organized, Orchestrated, Controlled, Chaired, Planned, Headed, Programmed, Operated
    Creation: Engineered, Created, Instituted, Formalized, Formulated, Founded, Spearheaded, Devised, Introduced, Formed, Developed, Launched
    Human Resources: Recruited, Hired, Cultivated, Shaped, Guided, Aligned, Regulated, Inspired, Directed, Supervised, Mentored
    Research: Calculated, Surveyed, Investigated, Evaluated, Tracked, Audited, Tested, Analyzed, Mapped, Examined, Assembled, Measured
    """

    resume_sections = """
    Order of sections:
    1. Contact Info
       - Email address (should be short, professional, and easy to type)
       - Phone
       - LinkedIn (should be formatted as Linkedin: Username and hyperlinked)
       - Github (should be formatted as Github: Username and hyperlinked)
    2. Education
       - Grad date (month and year, don't include starting date)
       - GPA
       - Major and Minor
       - Relevant Coursework
       - Technical Skills
       - Languages
       - Tools & Frameworks
       - Certifications
    3. Work Experience/ Research
       - Should include internships, research experience, TA experience, Tutoring experience, and any other paid experience
       - Bullet points should be formatted using Question model explained in bullet point guidelines
    4. Projects
       - Should include class, personal, or open source projects
       - Bullet points should be general overview of project and include technologies utilized
       - No more than 3 one line bullet points should be used, preferably use 2
    5. Leadership Experience
       - Should include organizations, awards, scholarships, and any other extracurricular activities
       - If you run out of space, you can create 2 columns
    """

    system_prompt = f"""
    You are an expert resume reviewer for a {job_details["job_title"]} internship or new grad role at {job_details["company"]}. Your review should be highly detailed and focused on the following aspects:

    Ensure the resume aligns with the job's qualifications.
    - Minimum Qualifications: {job_details["min_qual"]}
    - Preferred Qualifications: {job_details["pref_qual"]}

    Here are the key guidelines for resume writing:

    {dos_and_donts}

    {bullet_point_guidelines}

    Resume sections should be in this order:
    {resume_sections}

    Here are the extracted text elements of the default resume for comparison:
    {json.dumps(extracted_data_jake_resume, indent=2)}

    Here are your guidelines for a great bullet point:
    - It starts with a strong, relevant action verb that pertains to {job_details["job_title"]} or related technical roles.
    - It is specific, technical, and directly related to {job_details["job_title"]} tasks or achievements.
    - It talks about significant, measurable achievements within a {job_details["job_title"]} context.
    - It is concise and professional. No fluff or irrelevant details.
    - If possible, it quantifies impact, especially in technical or {job_details["job_title"]}-related terms.
    - Two lines or less.
    - Does not have excessive white space.
    - Avoids any mention of irrelevant skills, hobbies, or experiences that do not directly contribute to a {job_details["job_title"]} role.

    Here are your guidelines for giving feedback:
    - Be kind, but firm.
    - Be specific.
    - Be actionable.
    - Ask questions like "how many...", "how much...", "what was the technical impact...", "how did this experience contribute to your {job_details["job_title"]} skills...".
    - Be critical about the relevance of the content to a {job_details["job_title"]} role.
    - If the bullet point is NOT a 10/10, then the last sentence of your feedback MUST be an actionable improvement item focused on how to make the experience or achievement more relevant to software engineering.

    Here are your guidelines for rewriting bullet points:
    - If the original bullet point is a 10/10 and highly relevant to {job_details["job_title"]}, do NOT suggest any rewrites.
    - If the original bullet point is not a 10/10 or not relevant to {job_details["job_title"]}, suggest 1-2 rewrite options that make the content more technical, professional, and directly related to the field.
    - Be 1000% certain that the rewrites address all of your feedback.

    Here are your guidelines for great formatting:
    - Ensure consistency in font size and type.
    - Align bullet points and headings properly.
    - Check for sufficient spacing between sections.
    - Ensure clear and readable section headings.
    - Highlight important details without overwhelming with too much text.
    - Be particularly critical of resumes that include unprofessional language, irrelevant experiences, or inappropriate formatting.

    Here are your guidelines for giving formatting feedback:
    - Compare the user's resume formatting to the default resume.
    - Identify specific formatting issues in the user's resume.
    - Explain why each identified issue is problematic for a {job_details["job_title"]} resume.
    - Be precise in describing the location and nature of formatting problems.
    - Acknowledge any formatting aspects that are well-executed.

    Here are your guidelines for suggesting formatting improvements:
    - If the formatting is a 10/10, do not suggest any improvements.
    - If the formatting is not a 10/10, provide 1-2 suggestions that are clear, specific, and actionable to address each formatting issue.
    - Explain how each improvement will enhance the resume's readability and professionalism.
    - Prioritize formatting changes that will have the most impact for a {job_details["job_title"]} position.
    - If applicable, reference the default resume as an example of good formatting.
    - Suggest tools or techniques (e.g., specific word processor features) that can help implement the improvements.
    - Emphasize the importance of consistency throughout the resume.
    """
    # Check if the resume is a single page
    is_single_page_user_resume = check_single_page(resume_user )

    # Extract text and formatting information
    extracted_data_user_resume = extract_text_and_formatting(resume_user)

    logger.debug(f"Extracted data: {extracted_data_user_resume}")

    # Ensure extracted_data is a dictionary
    if not isinstance(extracted_data_user_resume, dict):
        logger.error("Extracted user resume data is not a dictionary.")
        raise ValueError("Extracted user resume data must be a dictionary.")

    formatting_info_user_resume = extracted_data_user_resume["formatting"]

    # Example of processing formatting_info
    for index, item in enumerate(formatting_info_user_resume):
        # Ensure item is a dictionary
        if isinstance(item, dict):
            text = item.get("text")
            font = item.get("font")
            size = item.get("size")
            bbox = item.get("bbox")
            
            # Log the extracted formatting information
            logger.info(f"Formatting info [{index}]: text='{text}', font='{font}', size={size}, bbox={bbox}")
        else:
            logger.error(f"Formatting info item at index {index} is not a dictionary: {item}")

    # Analyze font consistency
    font_consistency_feedback = analyze_font_consistency(formatting_info_user_resume)

    # Adjust feedback based on page count
    if not is_single_page_user_resume:
        logger.warning("The resume is more than one page.")
        additional_feedback = "Your resume exceeds one page. Consider condensing your content to fit on a single page for better readability."
    else:
        additional_feedback = "Your resume is appropriately formatted to fit on a single page."


    logger.info("FONT CONSISTENCY: ", font_consistency_feedback['feedback'])

    user_prompt = f"""
    Please review this resume for the role of {job_title} at {company}. 
    The first image is the user's resume, and the second image is the default resume for comparison.
    The job's minimum qualifications are as follows:
    {min_qual}
    The job's preferred qualifications are as follows:
    {pref_qual}
    Here are the extracted text elements with their bounding box information:
    {json.dumps(extracted_data_user_resume, indent=2)}
    Additional feedback: {additional_feedback}
    Now, compare the formatting of this resume with the default resume data provided in the system prompt.
    
    IMPORTANT: Keep all feedback strings concise and under 200 characters each. Be direct and specific.
    
    Only return JSON that respects the following schema:
    experiences: [
        {{
            bullets: [
                {{
                    content: string,
                    feedback: string,
                    rewrites: [string, string],
                    score: number
                }}
            ],
            company: string,
            role: string
        }}
    ],
    projects: [
        {{
            bullets: [
                {{
                    content: string,
                    feedback: string,
                    rewrites: [string, string],
                    score: number
                }}
            ],
            title: string
        }}
    ],
    formatting: {{
        font_consistency: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        font_choice: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        font_size: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        alignment: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        margins: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        line_spacing: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        section_spacing: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        headings: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        bullet_points: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        contact_information: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        overall_layout: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        page_utilization: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        is_single_page: {{ issue: {not is_single_page_user_resume}, feedback: {additional_feedback}, suggestions: [string, string], score: {10 if is_single_page_user_resume else 0} }},
        consistency: {{ issue: boolean, feedback: string, suggestions: [string, string], score: number }},
        overall_score: number
    }}
    """

    image_base64_user_resume = convert_pdf_to_image(resume_user)
    image_base64_jake_resume = convert_pdf_to_image(resume_jake)
    
    messages = [
        {
            'role': 'user',
            'content': [
                {'type': 'text', 'text': f"Here is the user's resume: "},
                {'type': 'image', 'source': {'data': image_base64_user_resume, 'media_type': 'image/png', 'type': 'base64'}},
                {'type': 'text', 'text': f"Here is the default resume: "},
                {'type': 'image', 'source': {'data': image_base64_jake_resume, 'media_type': 'image/png', 'type': 'base64'}},  
                {'type': 'text', 'text': user_prompt}       
            ]
        }
    ]

    encoding = tiktoken.encoding_for_model("gpt-4o")
    num_tokens = len(encoding.encode(user_prompt)) + len(encoding.encode(system_prompt))
    logger.info(f"Number of tokens in user and system prompt: {num_tokens}")
    
    try:
        completion = get_chat_completion(max_tokens=8192, messages=messages, system=system_prompt, temperature=0.25)
        logger.info(f"Result structure: {completion}")
        
        # Strip markdown code blocks if present
        completion = completion.strip()
        if completion.startswith("```json"):
            completion = completion[7:]  # Remove ```json
        elif completion.startswith("```"):
            completion = completion[3:]  # Remove ```
        if completion.endswith("```"):
            completion = completion[:-3]  # Remove trailing ```
        completion = completion.strip()
        
        # The completion should be a JSON string directly from the API
        try:
            result = json.loads(completion)
            logger.info(f"Parsed result: {result}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from completion: {e}")
            logger.error(f"Raw completion: {completion}")
            raise ValueError(f"Invalid JSON response from API: {e}")
        
        resume_feedback = ResumeFeedback(**result)
        logger.info("Resume reviewed and feedback generated successfully")
        resume_feedback_model = resume_feedback.dict()
        logger.info(resume_feedback_model)
        return resume_feedback.dict()
    except ValidationError as e:
        logger.error(f"Validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Error processing resume: {str(e)}")
        raise