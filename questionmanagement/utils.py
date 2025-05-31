"""
Utility functions for the Avirta platform.
"""

def calculate_score(hits, misses, time_bonus=0):
    """
    Calculate a player's score based on hits, misses, and time bonus.
    
    Args:
        hits (int): Number of successful hits
        misses (int): Number of misses
        time_bonus (int, optional): Additional points for quick completion. Defaults to 0.
        
    Returns:
        int: The calculated score
    """
    base_score = (hits * 100) - (misses * 50)
    total_score = max(0, base_score + time_bonus)
    return total_score