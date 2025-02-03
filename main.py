from typing import Dict, List
from autogen import ConversableAgent
import re
import string
import sys
import os
import math
from dotenv import load_dotenv

# Load the .env file
load_dotenv()


def sanitize(name):
    SPACES = re.compile(r'\s+')
    VALID_CODE_CHARS = set(string.ascii_lowercase + string.digits)
    return ''.join(c for c in SPACES.sub('', name).strip().lower() if c in VALID_CODE_CHARS).strip()


def fetch_restaurant_data(restaurant_name: str) -> Dict[str, List[str]]:
    ''' This function takes in a restaurant name and returns the reviews for that restaurant. 
    The output should be a dictionary with the key being the restaurant name and the value being a list of reviews for that restaurant. '''

    sanitized_name = sanitize(restaurant_name)
    restaurant_data = {restaurant_name: []}
    with open('restaurant-data.txt', 'r') as file:
        for line in file:
            restaurant, review = line.split('.', 1)
            restaurant = restaurant.strip()
            review = review.strip()
            if sanitize(restaurant) == sanitized_name:
                restaurant_data[restaurant_name].append(review)
    return restaurant_data


def calculate_overall_score(restaurant_name: str, food_scores: List[int], customer_service_scores: List[int]) -> Dict[str, float]:
    ''' This function takes in a restaurant name, a list of food scores from 1-5, and a list of customer service scores from 1-5
     The output should be a score between 0 and 10, which is computed as the following:
     SUM(sqrt(food_scores[i]**2 * customer_service_scores[i]) * 1/(N * sqrt(125)) * 10
     The above formula is a geometric mean of the scores, which penalizes food quality more than customer service. '''

    len_food_scores = len(food_scores)
    len_customer_service_scores = len(customer_service_scores)
    N = min(len_food_scores, len_customer_service_scores)
    overall_score = 0
    for i in range(N):
        overall_score += ((math.sqrt((food_scores[i] ** 2) * (customer_service_scores[i])) * (1/(N * math.sqrt(125)))) * 10)
    overall_score = round(overall_score, 2)
    return {restaurant_name: overall_score}


def get_entrypoint_agent_prompt() -> str:
    return '''
        You are a helpful agent for restaurant reviews who can do any of the two things (only one at a time):
        1. If I give you the overall score of a restaurant in the query then you return me that score and terminate the conversation.
        Do not do any formatting on it and make it three decimal places. And refrain from giving any number or overall score that is not in the context.
        2. Otherwise, just return me the query I give you as it is without doing anything to it.
        Do no make any other comments or analysis.
    '''


def get_data_fetch_agent_prompt() -> str:
    return '''
        You are a helpful agent who can do any of the two things (only one at a time):
        1. If and only if I give you a query asking for a restaurant review, just extract and return the resturant name from that query;
        do nothing else except returning the name.
        2. However, if I give you a list of reviews from a restaurant return those review to me as is without doing any scoring or analysis;
        I will just need the reviews list back as is.
        Do no make any other comments or analysis.
    '''


def get_review_analysis_agent_prompt() -> str:
    return '''
        You will read a list of reviews for a restaurant and assign each review a food_score and a customer_service_score.
        You will extract these two scores by looking for keywords in the review. Here are the keywords you should look out for:
        Score 1/5 has one of these adjectives: awful, horrible, or disgusting.
        Score 2/5 has one of these adjectives: bad, unpleasant, or offensive.
        Score 3/5 has one of these adjectives: average, uninspiring, or forgettable.
        Score 4/5 has one of these adjectives: good, enjoyable, or satisfying.
        Score 5/5 has one of these adjectives: awesome, incredible, or amazing.
        Each review will have exactly only two of these keywords, one for describing food and and one for customer service, and the score (out of 5) is 
        only determined through the above listed keywords. No other factors go into score extraction.
        Apart from what I wrote above, do no make any other comments or analysis.
    '''


def get_scoring_agent_prompt() -> str:
    return '''
        You are a helpful agent. You will be given some reviews (each review on a new line) with food_scores and customer_service_scores.
        Every line of review will have the following format:

        <review number>. food_score: <food_score>, customer_service_score: <customer_service_score>

        All scores will be out of 5 and your job is to create two lists of integers:
        1. A list of all food scores (integers)
        2. A list of all customer service scores (integers)
        Do no make any other comments or analysis.
    '''


# Do not modify the signature of the "main" function.
def main(user_query: str):
    # the main entrypoint/supervisor agent
    entrypoint_agent = ConversableAgent(
        "entrypoint_agent", 
        system_message=get_entrypoint_agent_prompt(), 
        llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": os.environ.get("OPENAI_API_KEY")}]},
        human_input_mode="NEVER",
    )
    entrypoint_agent.register_for_execution(name="fetch_restaurant_data")(fetch_restaurant_data)
    entrypoint_agent.register_for_execution(name="calculate_overall_score")(calculate_overall_score)


    data_fetch_agent = ConversableAgent(
        "data_fetch_agent", 
        system_message=get_data_fetch_agent_prompt(), 
        llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": os.environ.get("OPENAI_API_KEY")}]},
        human_input_mode="NEVER",
    )
    data_fetch_agent.register_for_llm(name="fetch_restaurant_data", description="Fetches the reviews for a specific restaurant.")(fetch_restaurant_data)

    review_analysis_agent = ConversableAgent(
        "review_analysis_agent", 
        system_message=get_review_analysis_agent_prompt(),
        llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": os.environ.get("OPENAI_API_KEY")}]},
        human_input_mode="NEVER",
    )

    scoring_agent = ConversableAgent(
        "scoring_agent", 
        system_message=get_scoring_agent_prompt(),
        llm_config={"config_list": [{"model": "gpt-4o-mini", "api_key": os.environ.get("OPENAI_API_KEY")}]},
        human_input_mode="NEVER",
    )
    scoring_agent.register_for_llm(name="calculate_overall_score", description='''
        Calculates the overall score for a resturant when given a restaurant name, a list of food scores and a list of customer service scores.
    ''')(calculate_overall_score)

    result = entrypoint_agent.initiate_chats([
        {
            "recipient": data_fetch_agent,
            "message": f'''{user_query}. Once you have fetched all the reviews of the restaurant, end the chat.''',
            "max_turns": 2,
            "clear_history": True,
            "summary_method": "last_msg",
        },
        {
            "recipient": review_analysis_agent,
            "message": 'These are the reviews for the restaurant',
            "max_turns": 1,
            "summary_method": "last_msg",
        },
        {
            "recipient": scoring_agent,
            "message": 'These are the reviews for the restaurant. Once you get the overall score number just return that and end the chat.',
            "max_turns": 4,
            "max_consecutive_auto_reply": 1,
            "summary_method": "last_msg",
        },
        {
            "recipient": entrypoint_agent,
            "message": 'What is the overall score of the restaurant. Answer only from the overall score number passed in the context.',
            "max_turns": 1,
            "summary_method": "last_msg",
        },
    ])
    print("Chat Summary: ", result[-1].summary)


# DO NOT modify this code below.
if __name__ == "__main__":
    assert len(sys.argv) > 1, "Please ensure you include a query for some restaurant when executing main."
    main(sys.argv[1])
