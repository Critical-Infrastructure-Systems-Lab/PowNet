# Contributing to PowNet 2.0

Thank you for your interest in contributing to PowNet 2.0! We are excited to welcome new members to our community.
Whether you're looking to fix a bug, add a new feature, improve documentation, or share your examples; your
contributions are highly valuable to us.

This document provides guidelines to help you get started with contributing to PowNet.

## Code of Conduct

While PowNet 2.0 currently has a small community, we are committed to fostering an open, welcoming,
and respectful environment for everyone. We expect all contributors to be respective and considerate with
other members.

Our formal [code of conduct](https://github.com/Critical-Infrastructure-Systems-Lab/PowNet/blob/master/docs/.github/CODE_OF_CONDUCT.md) is also available.


## Ways to contribute

There are many ways you can contribute to PowNet 2.0. Here are some examples:

* **Reporting bugs**: If you encounter a bug, please open an issue tracker. Provide as much detail as possible,
  including steps to reproduce the bug, your environment, the error message, and, if possible, your power system model.

* **Fixing bugs:** If you see an open bug report that you think you can fix, feel free to work on it. It would also help
  the community to let others know you plan to tackle it.

* **Suggesting enhancements**: If you have an idea for a new feature or improvement (especially computational aspects),
  please feel free to open an issue to discuss it.

* **Add a new feature**: You can contribute new functionalities, such as:
  - New unit commitment formulations (working with the optim_model module)
  - New solution algorithms (working with the optim_model module)

* **Refactoring code**: PowNet 2.0 was born out of research code, so there is always a potential area to improve the code in terms of
  readability, maintainability, and performance. For significant refactoring, please open an issue to discuss your proposed changes and
  coordinate with our maintainers to avoid conflicts. Our code is used by many research groups around the world!

* **Improving documentation**: You can help with improving our documentation by revising current documentations, adding new ones, and correcting typos
  and grammartical errors.

* **Adding unit tests**: Help us ensure the stability and realiability by reviewing existing unit tests and even write new ones.

* **Adding examples**: We welcome interesting ways to use PowNet!


## Getting started on your first contribution

Here is how to make a contribution:

1. Familiarize yourself with the codebase by understanding its structure and conventions (coding style and variable naming conventions)
2. Find an issue or propose a change. You can look for existing issues, especially those with labels like `good first issue` or `help wanted` in our issue tracker.
   If you want to work on something not yet tracked, please open a new issue and provide a clear description or the desired feature.

   *Note*: for big changes, please discuss your intended approach with our maintainers before you start coding. This helps ensure that
   we are using everyone's time efficiently and the development aligns with the project's direction.
   
4. Setting up your Python environment
   - Fork the PowNet 2.0 repository to your local machine, install dependencies within your virtual environment and start coding!
5. Following establish coding practices, such as
   - Adopt the project's coding styles and naming convention (more on this below)
   - Use `Black` to automatically format your code
   - Lint your code with `Flake8`
6. Commt your changes -- make small, and logical commits
7. Submit a pull request (PR) from your branch to the project's default or designated branch as agreed upon in the issue discussion

## Coding style and conventions

To streamline development and maintain readability, we adhere to the following.

* [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
* Existing coding style, naming coventions, and architectural patterns already present in the codebase
* Type hinting is encouraged because we automatically generate code documentation
* Code formatting using [Black](https://github.com/psf/black)
* We use [Flake8](https://flake8.pycqa.org/en/latest/) for linting to catch common errors and style issues


## Running unit tests

PowNet 2.0 uses Python's built-in `unittest` framework to ensure code quality and prevent regressions. These tests are located in the `src/test_pownet` directory.
To run all unit tests, navigate to the root PowNet directory in your terminal and execute:

  ```bash
  python -m unittest discover src/test_pownet
  ```

`Note`: contributions that add new code should include a corresponding unit test. When existing code is modified, ensure all tests pass before submitting a PR.


## Writing commit messages

For newer commits, we follow the [Conventional Commits](https://www.conventionalcommits.org/) specification for the commit messages. This conventional leads to more
readable commit histories and helps automate changelog generation.

A commit message should be structured as ```(commit type): description```. Common commit types are as follow.

* `fix`: A commit that patches a bug in your codebase
* `feat`: A commit that introduces a new feature to the codebase
* `docs`: Documentation only changes.
* `style`: Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc).
* `refactor`: A code change that neither fixes a bug nor adds a feature.
* `perf`: A code change that improves performance.
* `test`: Adding missing tests or correcting existing tests.
* `ci`: Changes to our CI configuration files and scripts (example scopes: GitHub, Read the Docs)
* `build`: Changes that affect the build system or external dependencies (example: update package versions)
* `chore`: Other changes that don't modify `src` or `test` files.

**Note on breaking changes**: A breaking change makes the code backward incompatible. Examples include rename/remove/modify existing functions, classes, or methods.
For these changes, please append a `!` after the commity type like `refactor!: ModelBuilder class`.


## Submitting a Pull Request (PR)

When you're ready to submit your changes:

1.  Ensure your pull request targets the correct branch in the upstream PowNet 2.0 repository. This will typically be the `main` or `dev` branch, or a specific feature branch as agreed upon in the issue discussion.
2.  Provide a clear title and description:
    * Write a clear and descriptive title for your PR that summarizes the changes.
    * In the PR description, provide a detailed explanation of what your changes do and why they are needed.
    * Link to relevant issues using keywords like `Closes #123` or `Fixes #456`.
3.  Before submitting, review your own changes one last time (the "diff"). Check for any typos, debugging code, or unintended changes.
4.  After submitting your PR, automated checks (Continuous Integration - CI) will run. These typically include running linters, formatters, and unit tests. The outputs
    can be found on GitHub's `Action` tab. If your PR fails a build or test, investigate the cause and push new commits to your branch to fix it.
6.  Project maintainers and other contributors may review your code and provide feedback. Be open to discussion and willing to make further changes if requested.


## Code Review Process

Code review is a critical part of our development process. It helps maintain code quality, share knowledge, and improve the overall project.

**For Reviewers:**

* Focus on the technical aspects of the code not the author. Provide constructive criticism aimed at improving the code.
* Clearly explain your reasoning and suggest concrete improvements. Don't just say "this is bad", but explain the problem and offer alternatives.
* Check for correctness, clarity, performance, test coverage, and adherence to coding standards.
* Review PRs in a timely manner.

**For Authors:**

* When your code is critiqued, questioned, or constructively criticized, remember that this is part of the collaborative process. Do not take code review personally.
* We trust that you've done your best with the knowledge you have. Mistakes happen, and code review is a chance to catch them.
* Address all comments and questions from reviewers. If you disagree with a suggestion, explain your reasoning respectfully.

## Questions and Discussions

If you have questions about the codebase, a specific issue, or the contribution process, please share your thoughts or questions on GitHub discussions.

