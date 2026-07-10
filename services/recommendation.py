def generate_recommendation(
    crop,
    predicted_price,
    current_price
):


    difference = (
        predicted_price-current_price
    )



    if difference > 500:

        return {

        "advice":
        "Prices are expected to rise. Consider storing produce.",


        "action":
        "WAIT"

        }



    elif difference < -500:


        return {


        "advice":
        "Prices may fall. Consider selling soon.",


        "action":
        "SELL"

        }



    else:


        return {


        "advice":
        "Market is stable. Sell based on your needs.",


        "action":
        "NORMAL"

        }
