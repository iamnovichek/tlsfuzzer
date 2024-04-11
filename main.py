import os
import logging

logger = logging.getLogger("tester")
logger.setLevel(logging.INFO)

terminal = logging.StreamHandler()
terminal.setLevel(logging.INFO)

logger.addHandler(terminal)


def get_test_name(file_name):
    fname = file_name.split(".")[0].split("test-")[1]

    return " ".join(fname.split("-")).upper()


def run_tests(tests_list, website_name):
    for test in tests_list:
        logger.info("\nTests: " + str(tests_list.index(test) + 1) + "/" + str(len(tests_list)) + "\n")
        text = "\n" + ("-" * 50) + "\n" + " TESTING " + get_test_name(test) + "\n" + ("-" * 50)
        logger.info(text)

        os.system("PYTHONPATH=. python3 scripts/" + test + " -h " + website_name + " -p 443")


if __name__ == "__main__":
    all_files = os.listdir("./scripts/")

    tests = [file for file in all_files if "test" in file]

    website_name = input("Enter your website domain name: \n")

    run_tests(tests, website_name)

    logger.info("\n\n")
    logger.info("============================================================")
    logger.info("======================== DONE !!! ==========================")
    logger.info("============================================================")

