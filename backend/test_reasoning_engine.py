"""
Test RUTE's Reasoning & Learning System
The MILLION-DOLLAR FEATURE that makes RUTE truly valuable!

This script demonstrates:
1. How RUTE logs its complete thought process
2. How to access RUTE's reasoning for each decision
3. How RUTE learns from winning and losing trades
4. How to view learning insights and performance analytics
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:8000"


def setup_auto_trading_for_demo():
    """Setup auto-trading with paper account for demo purposes"""
    print("\n" + "="*70)
    print("STEP 1: Setting up Auto-Trading (Paper Trading)")
    print("="*70)

    config = {
        "enabled": True,
        "broker_config": {
            "broker_type": "alpaca",
            "api_key": "DEMO_API_KEY",  # Replace with real key for actual trading
            "api_secret": "DEMO_SECRET",  # Replace with real secret
            "paper_trading": True
        },
        "max_position_size": 1000,
        "max_daily_loss": 500,
        "min_confidence": 60
    }

    try:
        response = requests.post(f"{BASE_URL}/api/auto-trade/setup", json=config)
        result = response.json()
        print(json.dumps(result, indent=2))
        return result.get("success", False)
    except Exception as e:
        print(f"Note: {e}")
        print("This is expected if you haven't set up broker credentials yet.")
        return False


def generate_ml_recommendation_with_reasoning():
    """
    Generate ML recommendations
    This will trigger RUTE's complete thought logging!
    """
    print("\n" + "="*70)
    print("STEP 2: Generating ML Recommendations with Thought Logging")
    print("="*70)
    print("\nRUTE will now analyze the market and LOG its complete thought process:")
    print("  - What it observes in market data")
    print("  - How it interprets technical indicators")
    print("  - Why it predicts BUY/SELL")
    print("  - What confidence level and why")

    request_data = {
        "symbols": [
            {"symbol": "AAPL", "assetType": "stock"},
            {"symbol": "TSLA", "assetType": "stock"},
            {"symbol": "GOOGL", "assetType": "stock"}
        ],
        "riskSettings": {
            "maxPositionSize": 1000,
            "maxDailyLoss": 500,
            "stopLossPercentage": 2,
            "takeProfitPercentage": 6,
            "enableAutoTrade": False  # Just generating recommendations for now
        }
    }

    print("\nGenerating recommendations...")
    response = requests.post(f"{BASE_URL}/api/recommendations", json=request_data)
    result = response.json()

    print(f"\n✓ Generated {len(result['recommendations'])} recommendations:")
    for rec in result['recommendations']:
        print(f"\n  {rec['symbol']}: {rec['type']}")
        print(f"    Entry: ${rec['entryPrice']:.2f}")
        print(f"    Confidence: {rec['confidence']}%")
        print(f"    Reasoning: {rec['reasoning']['summary'][:100]}...")

    return result


def view_rute_thoughts_for_symbol(symbol: str):
    """
    View RUTE's complete thought process for a symbol
    THIS IS THE MILLION-DOLLAR FEATURE!
    """
    print("\n" + "="*70)
    print(f"STEP 3: Viewing RUTE's Thoughts for {symbol}")
    print("="*70)
    print("\nThis shows EXACTLY why RUTE made its decision:")

    try:
        response = requests.get(f"{BASE_URL}/api/thoughts/{symbol}")
        thoughts = response.json()

        if "error" in thoughts:
            print(f"\n⚠️  {thoughts['error']}")
            print("\nNote: Thoughts will be logged when auto-trading is enabled")
            print("or when you execute trades.")
            return None

        # Display Analysis Thoughts
        if thoughts.get("analysis"):
            print("\n📊 ANALYSIS THOUGHTS:")
            for i, analysis in enumerate(thoughts["analysis"], 1):
                print(f"\n  Analysis #{i} at {analysis['timestamp']}")
                print(f"  Observation: {analysis['thought']['observation']}")
                if 'technical_analysis' in analysis['thought']:
                    tech = analysis['thought']['technical_analysis']
                    print(f"  Technical Indicators: {', '.join(tech.get('indicators', [])[:3])}")
                    print(f"  Market Trend: {tech.get('market_trend', 'N/A')}")
                if 'ml_analysis' in analysis['thought']:
                    ml = analysis['thought']['ml_analysis']
                    print(f"  ML Prediction: {ml.get('prediction', 'N/A')}")
                    print(f"  ML Confidence: {ml.get('confidence', 0)}%")

        # Display Decision Thoughts
        if thoughts.get("decisions"):
            print("\n🧠 DECISION THOUGHTS:")
            for i, decision in enumerate(thoughts["decisions"], 1):
                print(f"\n  Decision #{i} at {decision['timestamp']}")
                print(f"  Decision: {decision['thought']['decision']}")
                if 'reasoning_chain' in decision['thought']:
                    print(f"\n  Reasoning Chain (step-by-step):")
                    for step in decision['thought']['reasoning_chain'][:5]:
                        print(f"    • {step}")
                    if len(decision['thought']['reasoning_chain']) > 5:
                        print(f"    ... ({len(decision['thought']['reasoning_chain']) - 5} more steps)")

                if 'alternatives_considered' in decision['thought']:
                    print(f"\n  Alternatives Considered:")
                    for alt in decision['thought']['alternatives_considered']:
                        print(f"    • {alt['option']}")
                        print(f"      Rejected because: {alt['rejected_because']}")

        # Display Execution Thoughts
        if thoughts.get("executions"):
            print("\n⚡ EXECUTION THOUGHTS:")
            for i, execution in enumerate(thoughts["executions"], 1):
                print(f"\n  Execution #{i} at {execution['timestamp']}")
                exec_thought = execution['thought']
                print(f"  Action: {exec_thought.get('action', 'N/A')}")
                print(f"  Quantity: {exec_thought.get('quantity', 0)} shares")
                print(f"  Entry: ${exec_thought.get('entry_price', 0):.2f}")
                print(f"  Order ID: {exec_thought.get('order_id', 'N/A')}")

                if 'execution_thoughts' in exec_thought:
                    et = exec_thought['execution_thoughts']
                    print(f"  Why {et.get('order_type', 'N/A')} order: {et.get('why_market_order', 'N/A')}")

        # Display Outcome Thoughts (Learning!)
        if thoughts.get("outcomes"):
            print("\n🎯 OUTCOME THOUGHTS (What RUTE Learned):")
            for i, outcome in enumerate(thoughts["outcomes"], 1):
                print(f"\n  Outcome #{i} at {outcome['timestamp']}")
                out_thought = outcome['thought']
                print(f"  Result: {out_thought.get('outcome', 'N/A')}")

                if out_thought.get('outcome') == 'WIN':
                    print("\n  ✓ What Worked:")
                    for point in out_thought.get('what_worked', [])[:3]:
                        print(f"    • {point}")
                else:
                    print("\n  ✗ What Went Wrong:")
                    for point in out_thought.get('what_went_wrong', [])[:3]:
                        print(f"    • {point}")

                    print("\n  🔧 Corrective Actions:")
                    for action in out_thought.get('corrective_actions', [])[:3]:
                        print(f"    • {action}")

                if 'learning_points' in out_thought:
                    print("\n  📚 Learning Points:")
                    for point in out_thought['learning_points'][:3]:
                        print(f"    • {point}")

        return thoughts

    except Exception as e:
        print(f"\nError: {e}")
        return None


def view_learning_summary(days: int = 7):
    """
    View what RUTE has learned recently
    Shows patterns that work, mistakes to avoid, and performance
    """
    print("\n" + "="*70)
    print(f"STEP 4: What Has RUTE Learned? (Last {days} Days)")
    print("="*70)

    try:
        response = requests.get(f"{BASE_URL}/api/learning/summary?days={days}")
        summary = response.json()

        if "error" in summary:
            print(f"\n⚠️  {summary['error']}")
            print("\nNote: Learning summary requires auto-trading to be configured")
            return None

        print(f"\n📊 Performance Metrics:")
        metrics = summary.get('performance_metrics', {})
        print(f"  Total Trades: {metrics.get('total_trades', 0)}")
        print(f"  Win Rate: {metrics.get('win_rate', 0):.1f}%")
        print(f"  Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        print(f"  Average Win: ${metrics.get('average_win', 0):.2f}")
        print(f"  Average Loss: ${metrics.get('average_loss', 0):.2f}")

        print(f"\n✓ Successful Patterns Identified:")
        for pattern in summary.get('successful_patterns', [])[:5]:
            print(f"  • {pattern.get('pattern', 'N/A')}")
            print(f"    Occurrences: {pattern.get('count', 0)}, Win Rate: {pattern.get('win_rate', 0):.1f}%")

        print(f"\n✗ Mistakes to Avoid:")
        for mistake in summary.get('mistakes_learned', [])[:5]:
            print(f"  • {mistake.get('mistake', 'N/A')}")
            print(f"    Corrective Action: {mistake.get('corrective_action', 'N/A')}")

        print(f"\n🎯 Proposed Improvements:")
        for improvement in summary.get('proposed_improvements', [])[:3]:
            print(f"  • {improvement}")

        return summary

    except Exception as e:
        print(f"\nError: {e}")
        return None


def view_detailed_insights():
    """
    Get detailed performance analytics and learning insights
    """
    print("\n" + "="*70)
    print("STEP 5: Detailed Performance Analytics")
    print("="*70)

    try:
        response = requests.get(f"{BASE_URL}/api/learning/insights")
        insights = response.json()

        if "error" in insights:
            print(f"\n⚠️  {insights['error']}")
            return None

        print(f"\n📈 Learning Insights:")
        print(json.dumps(insights, indent=2))

        return insights

    except Exception as e:
        print(f"\nError: {e}")
        return None


def main():
    """
    Main demo of RUTE's reasoning and learning capabilities
    THE MILLION-DOLLAR FEATURE!
    """
    print("\n" + "="*70)
    print("RUTE REASONING & LEARNING ENGINE DEMO")
    print("="*70)
    print("\nThis is what makes RUTE worth $1,000,000+:")
    print("  * Complete transparency - see EXACTLY why RUTE trades")
    print("  * Full thought logging - every decision documented")
    print("  * Self-improvement - learns from wins AND losses")
    print("  * Pattern recognition - identifies what works")
    print("  * Mistake tracking - never makes the same error twice")

    # Step 1: Setup auto-trading (optional - just for demo)
    # setup_success = setup_auto_trading_for_demo()

    # Step 2: Generate ML recommendations with thought logging
    print("\n\n⏳ Generating recommendations and logging RUTE's thoughts...")
    recommendations = generate_ml_recommendation_with_reasoning()

    if recommendations and recommendations.get('recommendations'):
        # Pick the first symbol to analyze
        symbol = recommendations['recommendations'][0]['symbol']

        # Step 3: View RUTE's thoughts for that symbol
        view_rute_thoughts_for_symbol(symbol)

    # Step 4: View learning summary
    # Note: This requires auto-trading to be configured and some trades to have completed
    view_learning_summary(days=7)

    # Step 5: View detailed insights
    # view_detailed_insights()

    print("\n" + "="*70)
    print("✓ DEMO COMPLETE")
    print("="*70)
    print("\nKey Takeaways:")
    print("  1. RUTE logs EVERY decision it makes")
    print("  2. You can see the complete reasoning chain")
    print("  3. RUTE learns from both wins and losses")
    print("  4. Patterns are automatically identified")
    print("  5. Performance improves over time")
    print("\nTo enable full auto-trading with thought logging:")
    print("  1. Set up broker credentials (Alpaca recommended)")
    print("  2. Enable auto-trading via /api/auto-trade/setup")
    print("  3. RUTE will trade AND log all thoughts automatically")
    print("  4. Access thoughts via /api/thoughts/{symbol}")
    print("  5. View learning via /api/learning/summary")
    print("\n🚀 RUTE is ready to trade and explain its every decision!")


if __name__ == "__main__":
    main()
