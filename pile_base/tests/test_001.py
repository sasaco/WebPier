import conftest
# from src import initModel

def test_1Colum8Pile():

    pile = {
        "center": [
            ( 1.50, 9.00),
            ( 6.00, 9.00),
            (10.50, 9.00),
            (15.00, 9.00),
            ( 1.50, 5.25),
            ( 6.00, 5.25),
            (10.50, 5.25),
            (15.00, 5.25),
            ( 1.50, 1.50),
            ( 6.00, 1.50),
            (10.50, 1.50),
            (15.00, 1.50)
        ],
        "radius": 1.00
    }

    columns =  [
        ( 5.25, 2.75),
        ( 5.25, 7.75),
        (11.25, 7.75),
        (11.25, 2.75)
    ]

    footing = {
        "Area": [
            
        ]
    }

    assert True


if __name__ == "__main__":
    test_1Colum8Pile()
