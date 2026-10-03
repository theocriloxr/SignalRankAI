import asyncio
import asyncpg

async def test_passwords():
    passwords = ["", "postgres", "root", "password", "1234", "123456", "admin"]
    for pwd in passwords:
        try:
            conn = await asyncpg.connect(user="postgres", password=pwd, database="postgres", host="127.0.0.1", port=5432)
            print(f"Success with password: '{pwd}'")
            await conn.close()
            return
        except asyncpg.exceptions.InvalidPasswordError:
            pass
        except Exception as e:
            print(f"Error with '{pwd}': {e}")
    print("No password matched.")

if __name__ == "__main__":
    asyncio.run(test_passwords())
